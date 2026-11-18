"""HTTP access to a saved graph.

The command-line tool stays free of this module. Install the ``web`` extra
and run ``uvicorn osi.server:app``.
"""

from __future__ import annotations

import os
import re
import secrets
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import networkx as nx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from osi.ask import _execute
from osi.graph_utils import component_count, largest_subgraph, undirected_view
from osi.loader import load_edge_list, load_graphml
from osi.loaders.slack import detect_slack_format, load_slack_export
from osi.loaders.telegram import detect_telegram_format, load_telegram_export
from osi.loaders.whatsapp import detect_whatsapp_format, load_whatsapp_export, choose_edge_rule_from_sample
from osi.store import create_run, get_run, list_runs, load_graph, save_graph, store_path, _connection

app = FastAPI()

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _supplied_token(request: Request) -> str:
    supplied = request.headers.get("x-api-token", "")
    authorization = request.headers.get("authorization", "")
    if not supplied and authorization.lower().startswith("bearer "):
        supplied = authorization[7:]
    if not supplied:
        # The graph iframe and export buttons cannot set headers.
        supplied = request.query_params.get("token", "")
    return supplied


@app.middleware("http")
async def _api_auth(request: Request, call_next):
    """Require a token for API and graph traffic, or a loopback client when unset."""
    path = request.url.path
    if path.startswith("/api/") or path.startswith("/graph/"):
        token = os.environ.get("OSI_API_TOKEN")
        if token:
            supplied = _supplied_token(request)
            if not secrets.compare_digest(
                token.encode("utf-8"), supplied.encode("utf-8")
            ):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        else:
            host = request.client.host if request.client else ""
            if host not in _LOOPBACK_HOSTS:
                return JSONResponse(
                    {"detail": "Set OSI_API_TOKEN to allow non-local API clients."},
                    status_code=401,
                )
    return await call_next(request)


@app.on_event("startup")
async def _on_startup():
    _ensure_demo_run()


_STATIC = Path(__file__).resolve().parent / "static"
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class AskRequest(BaseModel):
    run: str
    question: str
    use_llm: bool = False
    use_agent: bool = False


def _static_file(path: str) -> Path:
    root = _STATIC.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return target


@app.get("/api/runs")
def get_runs() -> list[dict]:
    """Return a list of stored runs with details."""
    runs = []
    for run_id, source, created_at, notes in list_runs():
        # Load graph to get node/edge counts
        try:
            # Determine layer from config
            metadata = get_run(run_id)
            config = metadata.get("config") or {}
            layer = config.get("layer") or metadata.get("source")
            graph = load_graph(run_id, layer) if layer else None
            nodes = graph.number_of_nodes() if graph else 0
            edges = graph.number_of_edges() if graph else 0
        except Exception:
            nodes = 0
            edges = 0
        runs.append({
            "run_id": run_id,
            "source": source,
            "nodes": nodes,
            "edges": edges,
            "chat_name": notes or None,
        })
    return runs


@app.get("/api/runs/export")
def export_runs() -> dict:
    """Export the entire store as JSON."""
    data = {}
    tables = [
        "runs",
        "graphs",
        "metrics",
        "communities",
        "downloads",
        "results",
        "answer_cache",
        "metric_cache",
    ]
    with _connection() as conn:
        for table in tables:
            rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
            data[table] = [dict(row) for row in rows]
    return data


_IMPORT_TABLES = (
    "runs",
    "graphs",
    "metrics",
    "communities",
    "downloads",
    "results",
    "answer_cache",
    "metric_cache",
)
_IMPORT_DELETE_ORDER = (
    "metric_cache",
    "answer_cache",
    "results",
    "downloads",
    "communities",
    "metrics",
    "graphs",
    "runs",
)
_IMPORT_REQUIRED_COLUMNS = {
    "runs": {"id"},
    "graphs": {"run_id", "layer", "graph_json"},
    "metrics": {"run_id", "node", "metric", "value"},
    "communities": {"run_id", "node", "algorithm", "community_id"},
    "downloads": {"url"},
    "results": {"run_id", "source", "payload_json"},
    "answer_cache": {"key", "answer", "run_id"},
    "metric_cache": {"run_id", "metric", "result_json"},
}


def _validate_import(export_data: dict, conn) -> tuple[dict[str, list], dict[str, int]]:
    """Validate the payload before anything is deleted.

    Returns ``{table: [(columns, values), ...]}`` plus row counts.  Unknown
    tables, unknown columns, non-scalar values, and empty exports are refused.
    """
    if not isinstance(export_data, dict):
        raise HTTPException(status_code=400, detail="Import payload must be an object.")
    unknown = set(export_data) - set(_IMPORT_TABLES)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown import table(s): {', '.join(sorted(unknown))}",
        )
    runs = export_data.get("runs")
    if not isinstance(runs, list) or not runs:
        # An empty import used to delete every table and return success.
        raise HTTPException(
            status_code=400,
            detail="Refusing to import an export with no runs.",
        )

    table_columns = {
        table: {
            row["name"]
            for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        }
        for table in _IMPORT_TABLES
    }
    normalized: dict[str, list] = {}
    counts: dict[str, int] = {}
    for table, rows in export_data.items():
        if not isinstance(rows, list):
            raise HTTPException(
                status_code=400, detail=f"{table} must be a list of rows."
            )
        if not rows:
            normalized[table] = []
            counts[table] = 0
            continue
        if not all(isinstance(row, dict) for row in rows):
            raise HTTPException(
                status_code=400, detail=f"{table} contains a non-object row."
            )
        columns = list(rows[0].keys())
        if not columns or not set(columns) <= table_columns[table]:
            raise HTTPException(
                status_code=400,
                detail=f"{table} has unknown columns.",
            )
        required = _IMPORT_REQUIRED_COLUMNS[table]
        if not required <= set(columns):
            missing = ", ".join(sorted(required - set(columns)))
            raise HTTPException(
                status_code=400,
                detail=f"{table} is missing required column(s): {missing}",
            )
        prepared = []
        for row in rows:
            if set(row) != set(columns):
                raise HTTPException(
                    status_code=400,
                    detail=f"{table} rows do not share the same columns.",
                )
            values = tuple(row[column] for column in columns)
            if any(
                value is not None
                and not isinstance(value, (str, int, float, bool, bytes))
                for value in values
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"{table} contains a non-scalar value.",
                )
            prepared.append((columns, values))
        normalized[table] = prepared
        counts[table] = len(prepared)
    return normalized, counts


@app.post("/api/runs/import")
async def import_runs(export_data: dict) -> dict:
    """Import a store export after validating every table and column."""
    with _connection() as conn:
        normalized, counts = _validate_import(export_data, conn)
        conn.execute("SAVEPOINT osi_import")
        try:
            for table in _IMPORT_DELETE_ORDER:
                # A partial export replaces only the tables it carries; it must
                # not silently wipe tables the caller did not include.
                if table in normalized:
                    conn.execute(f'DELETE FROM "{table}"')
            for table, rows in normalized.items():
                for columns, values in rows:
                    column_sql = ", ".join(f'"{column}"' for column in columns)
                    placeholders = ", ".join("?" for _ in columns)
                    conn.execute(
                        f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})',
                        values,
                    )
            conn.execute("RELEASE SAVEPOINT osi_import")
        except Exception as error:
            conn.execute("ROLLBACK TO SAVEPOINT osi_import")
            conn.execute("RELEASE SAVEPOINT osi_import")
            raise HTTPException(
                status_code=400, detail=f"Import failed: {error}"
            ) from error
    return {"status": "success", "imported": counts}


@app.get("/api/runs/{run_id}")
def get_run_summary(run_id: str) -> dict:
    """Return compact graph metadata for the selected run."""
    metadata = get_run(run_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} was not found.")
    config = metadata.get("config") or {}
    layer = config.get("layer") or metadata.get("source")
    graph = load_graph(run_id, layer) if layer else None
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Graph for run {run_id} was not found.")
    return {
        "run": run_id,
        "source": metadata.get("source") or "unknown",
        "title": config.get("filename") or config.get("path") or run_id,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "components": component_count(graph),
    }


def _detect_source(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.casefold()
    if suffix == ".zip" and detect_slack_format(path) != "low":
        return "slack"
    if suffix == ".txt" and detect_whatsapp_format(path) != "low":
        return "whatsapp"
    if suffix == ".json" and detect_telegram_format(path) != "low":
        return "telegram"
    if suffix in {".csv", ".tsv", ".json"}:
        return "file"
    if suffix == ".graphml":
        return "file"
    return "unknown"


def _load_uploaded_graph(
    path: Path,
    source: str,
    edge_rule: str | None,
    window_minutes: float,
    thread_cap: int,
    chat_cap: int,
) -> tuple[nx.Graph, dict]:
    if source == "slack":
        confidence = detect_slack_format(path)
        if confidence == "low":
            raise ValueError("This file does not look like a Slack export ZIP.")
        rule = edge_rule or "thread"
        if rule not in {"thread", "channel", "mention"}:
            raise ValueError("Slack edge rule must be thread, channel, or mention.")
        graph, metadata = load_slack_export(path, edge_rule=rule, thread_cap=thread_cap)
        return graph, {"source": source, "title": metadata["workspace_name"]}
    if source == "telegram":
        confidence = detect_telegram_format(path)
        if confidence == "low":
            raise ValueError("This file does not look like a Telegram export JSON.")
        rule = edge_rule or "reply"
        graph, metadata = load_telegram_export(path, edge_rule=rule, chat_cap=chat_cap)
        return graph, {"source": source, "title": metadata["chat_title"]}
    if source == "whatsapp":
        if detect_whatsapp_format(path) == "low":
            raise ValueError("This file does not look like a WhatsApp text export.")
        if not edge_rule:
            # Use LLM to choose the edge rule
            chosen_rule, reasoning = choose_edge_rule_from_sample(path)
            print(f"[whatsapp] LLM chose edge rule: {chosen_rule} - {reasoning}", file=sys.stderr)
            edge_rule = chosen_rule
        else:
            edge_rule = edge_rule or "temporal"
        graph, metadata = load_whatsapp_export(
            path,
            edge_rule=edge_rule,
            window_minutes=window_minutes,
            chat_cap=chat_cap,
        )
        return graph, {"source": source, "title": metadata["chat_name"]}
    if source == "file":
        suffix = path.suffix.casefold()
        if suffix in {".csv", ".tsv", ".json"}:
            graph = load_edge_list(path)
        elif suffix == ".graphml":
            graph = load_graphml(path)
        else:
            raise ValueError("Choose a CSV, TSV, JSON, or GraphML file.")
        return graph, {"source": "file", "title": path.stem}
    raise ValueError("Could not recognize this file. Select its export format and try again.")


@app.post("/api/uploads")
async def upload_graph(
    file: UploadFile = File(...),
    source: str = Form("auto"),
    edge_rule: str = Form(""),
    window_minutes: float = Form(5),
    thread_cap: int = Form(30),
    chat_cap: int = Form(500),
) -> dict:
    """Parse an uploaded graph/export and save its graph under a generated run id."""
    allowed_sources = {"auto", "file", "slack", "telegram", "whatsapp"}
    if source not in allowed_sources:
        raise HTTPException(status_code=400, detail="Unknown source format.")
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".csv", ".tsv", ".json", ".graphml", ".txt", ".zip"}:
        raise HTTPException(status_code=400, detail="Unsupported file extension.")

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 50 MB limit.")

    try:
        with tempfile.TemporaryDirectory(prefix="osi-upload-") as directory:
            path = Path(directory) / filename
            path.write_bytes(content)
            detected_source = _detect_source(path, source)
            graph, metadata = _load_uploaded_graph(
                path,
                detected_source,
                edge_rule or None,
                window_minutes,
                thread_cap,
                chat_cap,
            )
    except (OSError, ValueError, nx.NetworkXError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if graph.number_of_nodes() == 0:
        raise HTTPException(status_code=400, detail="No senders or graph nodes were found.")

    layer = detected_source
    run_id = f"{detected_source}-{uuid4().hex[:8]}"
    config = {
        "source": detected_source,
        "layer": layer,
        "filename": filename,
        "edge_rule": edge_rule or None,
        "window_minutes": window_minutes,
        "thread_cap": thread_cap,
        "chat_cap": chat_cap,
    }
    create_run(detected_source, config, notes=filename, run_id=run_id)
    save_graph(run_id, layer, graph)
    components = component_count(graph)
    return {
        "run": run_id,
        "source": detected_source,
        "title": metadata.get("title") or filename,
        "filename": filename,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "components": components,
    }


@app.post("/api/ask")
def post_ask(req: AskRequest) -> dict:
    """Run the pipeline and return the answer plus metadata.

    ``ask`` returns only the sentence. ``_execute`` is the same pipeline
    and also returns intent, params, method, and trust.
    """
    # Determine source, node count, edge count for logging
    try:
        metadata = get_run(req.run)
        source = metadata.get("source") if metadata else "unknown"
        config = metadata.get("config") or {}
        layer = config.get("layer") or metadata.get("source")
        graph = load_graph(req.run, layer) if layer else None
        nodes = graph.number_of_nodes() if graph else 0
        edges = graph.number_of_edges() if graph else 0
    except Exception:
        source = "unknown"
        nodes = 0
        edges = 0
    print(f"[api] ask: run_id={req.run} source={source} nodes={nodes} edges={edges}", file=sys.stderr)

    started = time.perf_counter()
    try:
        text, query = _execute(
            req.run,
            req.question,
            req.use_llm,
            use_agent=req.use_agent,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    runtime_ms = int(round((time.perf_counter() - started) * 1000))
    return {
        "answer": text,
        "intent": query["intent"],
        "params": query["params"],
        "method": query["method"],
        "trust": query["trust"],
        "runtime_ms": runtime_ms,
    }


@app.get("/")
def index() -> FileResponse:
    """Serve the single HTML page."""
    return FileResponse(_static_file("index.html"))


@app.get("/static/{path:path}")
def static(path: str) -> FileResponse:
    """Serve static files from src/osi/static/."""
    return FileResponse(_static_file(path))


@app.get("/api/communities/{run_id}")
def api_communities(run_id: str) -> dict:
    import networkx as nx
    from osi.analysis import pagerank
    meta = get_run(run_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="run not found")
    layer = (meta.get("config") or {}).get("layer")
    graph = load_graph(run_id, layer) if layer else None
    if graph is None:
        raise HTTPException(status_code=404, detail="graph not found")
    try:
        view = undirected_view(graph)
        communities = list(nx.community.louvain_communities(view, seed=42))
    except Exception:
        return {"communities": []}
    pr = pagerank(view)
    out = []
    for i, members in enumerate(communities):
        n = len(members)
        max_internal = n * (n - 1) / 2
        internal = [(u, v) for u, v in view.edges() if u in members and v in members]
        density = len(internal) / max_internal if max_internal else 0
        hub = max(members, key=lambda m: pr.get(m, 0))
        hub_edges = sum(1 for u, v in internal if hub in (u, v))
        hub_share = hub_edges / len(internal) if internal else 0
        if density > 0.3 and hub_share < 0.6:
            verdict = "real"
        elif hub_share > 0.75 and density < 0.15:
            verdict = "hub"
        else:
            verdict = "mixed"
        out.append({"id": i, "size": n, "hub": hub, "density": round(density, 3),
                    "hub_share": round(hub_share, 2), "verdict": verdict})
    out.sort(key=lambda x: -x["size"])
    return {"communities": out}


@app.get("/api/tense/{run_id}")
def api_tense(run_id: str) -> dict:
    meta = get_run(run_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="run not found")
    layer = (meta.get("config") or {}).get("layer")
    graph = load_graph(run_id, layer) if layer else None
    if graph is None:
        raise HTTPException(status_code=404, detail="graph not found")
    rows = []
    for u, v, data in graph.edges(data=True):
        label = data.get("llm_label")
        if label in ("tense", "hostile", "condescending", "dismissive"):
            rows.append({"a": u, "b": v, "label": label,
                         "weight": data.get("weight", 1),
                         "message_count": data.get("message_count", 0),
                         "reason": (data.get("llm_reason") or "")[:200]})
    rows.sort(key=lambda r: -r["message_count"])
    return {"edges": rows}


@app.get("/graph/{run_id}")
def api_graph_html(run_id: str):
    from fastapi.responses import HTMLResponse
    from osi.viz import render_interactive_html
    import tempfile
    meta = get_run(run_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="run not found")
    layer = (meta.get("config") or {}).get("layer")
    graph = load_graph(run_id, layer) if layer else None
    if graph is None:
        raise HTTPException(status_code=404, detail="graph not found")
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        render_interactive_html(graph, tmp_path, top_edges=120, min_edge_weight=2.0, top_labels=40)
        html = Path(tmp_path).read_text(encoding="utf-8")
    finally:
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass
    return HTMLResponse(content=html)


def _ensure_demo_run() -> None:
    """Create wa-real from the bundled example if it doesn't exist yet."""
    import json as _json
    try:
        from osi.store import get_run, create_run as _create, save_graph as _save
        if get_run("wa-real") is not None:
            return
    except Exception:
        return

    root = Path(__file__).resolve().parents[2]
    fixture = root / "examples" / "whatsapp-demo.txt"
    labels_file = root / "examples" / "whatsapp-demo-edges.json"
    if not fixture.exists():
        return

    try:
        from osi.loaders.whatsapp import load_whatsapp_export
        graph, _meta = load_whatsapp_export(str(fixture), edge_rule="sequence")
    except Exception:
        return

    if labels_file.exists():
        try:
            labels = _json.loads(labels_file.read_text(encoding="utf-8"))
            for key, result in labels.items():
                if "|" not in key:
                    continue
                a, b = key.split("|", 1)
                if graph.has_edge(a, b):
                    graph[a][b]["llm_label"] = result.get("label")
                    graph[a][b]["llm_polarity"] = result.get("polarity")
                    graph[a][b]["llm_reason"] = result.get("reason")
        except Exception:
            pass

    try:
        rid = _create(
            "whatsapp",
            {"source": "whatsapp", "layer": "whatsapp", "edge_rule": "sequence",
             "path": str(fixture)},
            "WhatsApp sample",
            run_id="wa-real",
        )
        _save(rid, "whatsapp", graph)
    except Exception:
        pass


def main() -> None:
    """Start the local web server.

    The default bind address is loopback. Set ``OSI_HOST`` only when a reverse
    proxy or container network needs it, and set ``OSI_API_TOKEN`` in that case.
    """
    _ensure_demo_run()
    import uvicorn

    port = int(os.environ.get("PORT", "7860"))
    host = os.environ.get("OSI_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1", "localhost"} and not os.environ.get(
        "OSI_API_TOKEN"
    ):
        print(
            "[server] warning: binding a non-loopback address without "
            "OSI_API_TOKEN; API requests from other hosts will be rejected.",
            file=sys.stderr,
        )
    uvicorn.run(app, host=host, port=port)


@app.get("/api/graph/png/{run_id}")
async def get_graph_png(run_id: str):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise HTTPException(
            status_code=503, detail="matplotlib is required for PNG export."
        ) from error

    meta = get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Run not found")
    layer = (meta.get("config") or {}).get("layer")
    graph = load_graph(run_id, layer) if layer else None
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")
    if graph.number_of_nodes() == 0:
        raise HTTPException(status_code=400, detail="Graph is empty")

    view = undirected_view(graph)
    largest = largest_subgraph(view)

    # Gephi-style layout (high repulsion, strong gravity).
    pos = nx.spring_layout(
        largest, k=10.0 / max(1, len(largest) ** 0.5), iterations=200, seed=42
    )
    fig, ax = plt.subplots(figsize=(24, 24), facecolor="white")
    ax.set_facecolor("white")
    nx.draw_networkx_edges(
        largest, pos, alpha=0.08, edge_color="black", width=0.5, ax=ax
    )
    communities = list(nx.community.louvain_communities(largest, seed=42))
    node_comm = {node: i for i, group in enumerate(communities) for node in group}
    palette = [
        "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
        "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    ]
    node_colors = [
        palette[node_comm.get(node, 0) % len(palette)] for node in largest.nodes()
    ]
    node_sizes = [
        max(5, min(30, largest.nodes[node].get("message_count", 1) * 2))
        for node in largest.nodes()
    ]
    nx.draw_networkx_nodes(
        largest,
        pos,
        node_color=node_colors,
        node_size=node_sizes,
        linewidths=0,
        ax=ax,
    )
    ax.axis("off")

    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    png_path = handle.name
    handle.close()
    try:
        plt.savefig(
            png_path,
            dpi=300,
            bbox_inches="tight",
            facecolor="white",
            pad_inches=0,
        )
    except Exception:
        Path(png_path).unlink(missing_ok=True)
        raise
    finally:
        plt.close(fig)

    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
    return FileResponse(
        png_path,
        media_type="image/png",
        filename=f"lattice_{safe_id}.png",
        background=BackgroundTask(os.unlink, png_path),
    )


@app.post("/api/reddit")
async def api_reddit(payload: dict):
    from osi.loaders.reddit import load_subreddit
    from osi.store import create_run, save_graph, _connection
    subreddit = payload.get("subreddit", "AskReddit")
    limit = payload.get("limit", 1000)
    try:
        g, meta = load_subreddit(subreddit, limit=limit)
        
        config = {"subreddit": subreddit, "limit": limit, "layer": "whatsapp"}
        run_id = create_run("reddit", config)
        save_graph(run_id, "default", g)
        save_graph(run_id, "whatsapp", g)  # match the layer the endpoints look for
        
        return {"status": "ok", "run_id": run_id, "meta": meta}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/api/export/gexf/{run_id}")
async def export_gexf(run_id: str):
    meta = get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Run not found")
    layer = (meta.get("config") or {}).get("layer")
    graph = load_graph(run_id, layer) if layer else None
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".gexf")
    path = handle.name
    handle.close()
    try:
        nx.write_gexf(graph, path)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
    return FileResponse(
        path,
        media_type="application/gexf+xml",
        filename=f"lattice_{safe_id}.gexf",
        background=BackgroundTask(os.unlink, path),
    )


@app.get("/api/export/md/{run_id}")
async def export_md(run_id: str):
    from osi.analysis import pagerank

    meta = get_run(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Run not found")
    layer = (meta.get("config") or {}).get("layer")
    graph = load_graph(run_id, layer) if layer else None
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    view = undirected_view(graph)
    md = f"# Lattice Analysis: {run_id}\n\n"
    md += f"**Nodes:** {graph.number_of_nodes()} | **Edges:** {graph.number_of_edges()}\n\n"

    pr = pagerank(view)
    top_users = sorted(pr.items(), key=lambda item: item[1], reverse=True)[:10]
    md += "## Top 10 Users by PageRank\n"
    for node, score in top_users:
        md += f"- **{node}**: {score:.4f}\n"

    md += "\n## Communities (Louvain)\n"
    communities = list(nx.community.louvain_communities(view, seed=42))
    for index, group in enumerate(communities[:5]):
        md += (
            f"- **Group {index}**: {len(group)} members "
            f"(e.g., {', '.join(list(group)[:3])}...)\n"
        )

    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
    return PlainTextResponse(
        md,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=lattice_{safe_id}.md"},
    )


if __name__ == "__main__":
    main()
