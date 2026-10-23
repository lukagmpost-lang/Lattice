"""HTTP access to a saved graph.

The command-line tool stays free of this module. Install the ``web`` extra
and run ``uvicorn osi.server:app``.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import networkx as nx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from osi.ask import _execute
from osi.loader import load_edge_list, load_graphml
from osi.loaders.slack import detect_slack_format, load_slack_export
from osi.loaders.telegram import detect_telegram_format, load_telegram_export
from osi.loaders.whatsapp import detect_whatsapp_format, load_whatsapp_export, choose_edge_rule_from_sample
from osi.store import create_run, get_run, list_runs, load_graph, save_graph, store_path, _connection

app = FastAPI()


@app.on_event("startup")
async def _on_startup():
    _ensure_demo_run()


_STATIC = Path(__file__).resolve().parent / "static"
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class AskRequest(BaseModel):
    run: str
    question: str
    use_llm: bool = True
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
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = [dict(row) for row in rows]
    return data


@app.post("/api/runs/import")
async def import_runs(export_data: dict) -> dict:
    """Import the store from JSON exported by /api/runs/export."""
    with _connection() as conn:
        # Disable foreign key constraints temporarily
        conn.execute("PRAGMA foreign_keys = OFF")
        # Order of deletion: tables that depend on others first
        tables = [
            "metric_cache",
            "answer_cache",
            "results",
            "downloads",
            "communities",
            "metrics",
            "graphs",
            "runs",
        ]
        for table in tables:
            conn.execute(f"DELETE FROM {table}")
        # Insert the provided data
        for table, rows in export_data.items():
            if not rows:
                continue
            columns = ", ".join(rows[0].keys())
            placeholders = ", ".join(["?"] * len(rows[0]))
            insert_sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            for row in rows:
                conn.execute(insert_sql, tuple(row.values()))
        # Re-enable foreign keys and commit
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
    return {"status": "success", "message": "Store imported successfully"}
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
        "components": nx.number_connected_components(graph) if graph.number_of_nodes() else 0,
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
    components = nx.number_connected_components(graph)
    return {
        "run": run_id,
        "source": detected_source,
        "title": metadata.get("title") or filename,
        "filename": filename,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "components": components,
    }


@app.post("/api/converse")
async def api_converse(req: dict) -> dict:
    """Conversation loop: LLM writes code, iterates, answers."""
    from osi.converse import converse
    run_id = req.get("run_id")
    question = (req.get("question") or "").strip()
    history = req.get("history") or []
    if not run_id or not question:
        raise HTTPException(status_code=400, detail="run_id and question required")

    meta = get_run(run_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="run not found")
    layer = (meta.get("config") or {}).get("layer")
    if not layer:
        raise HTTPException(status_code=400, detail="run has no layer")
    graph = load_graph(run_id, layer)
    if graph is None:
        raise HTTPException(status_code=404, detail="graph not found")

    # Load messages from the run if available
    messages = []
    try:
        cfg = meta.get("config") or {}
        path = cfg.get("path")
        if path:
            from osi.loaders.whatsapp import _parse_export
            _, messages = _parse_export(path)
    except Exception:
        messages = []

    try:
        result = converse(question, graph, messages, verbose=False, history=history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"converse failed: {e}")

    return {
        "answer": result.get("answer", ""),
        "rounds": result.get("rounds", 0),
        "code_history": result.get("code_history", []),
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
        communities = list(nx.community.louvain_communities(graph, seed=42))
    except Exception:
        return {"communities": []}
    pr = pagerank(graph)
    out = []
    for i, members in enumerate(communities):
        n = len(members)
        max_internal = n * (n - 1) / 2
        internal = [(u, v) for u, v in graph.edges() if u in members and v in members]
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
    _ensure_demo_run()
    """Bind every interface. Render sets PORT; local use defaults to 7860.

    uvicorn reads the port at start. The request handlers do not.
    """
    import uvicorn

    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

@app.get("/api/graph/png/{run_id}")
async def get_graph_png(run_id: str):
    import os
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx
    from fastapi.responses import FileResponse
    from osi.store import get_run, load_graph

    meta = get_run(run_id)
    if not meta: return {"error": "Run not found"}
    layer = (meta.get("config") or {}).get("layer")
    g = load_graph(run_id, layer) if layer else None
    if not g: return {"error": "Graph not found"}

    # Keep largest connected component so the image is dense
    g_undir = g.to_undirected()
    largest_cc = max(nx.connected_components(g_undir), key=len)
    G = g.subgraph(largest_cc).copy()

    # Gephi-style layout (High repulsion, strong gravity)
    pos = nx.spring_layout(G, k=10.0/max(1, len(G)**0.5), iterations=200, seed=42)

    fig, ax = plt.subplots(figsize=(24, 24), facecolor='white')
    ax.set_facecolor('white')
    
    # Draw faint edges
    nx.draw_networkx_edges(G, pos, alpha=0.08, edge_color='black', width=0.5, ax=ax)

    # Draw nodes colored by community
    communities = list(nx.community.louvain_communities(G, seed=42))
    node_comm = {node: i for i, c in enumerate(communities) for node in c}
    PALETTE = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC"]
    node_colors = [PALETTE[node_comm.get(n, 0) % len(PALETTE)] for n in G.nodes()]
    node_sizes = [max(5, min(30, G.nodes[n].get("message_count", 1) * 2)) for n in G.nodes()]
    
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes, linewidths=0, ax=ax)
    ax.axis('off')

    png_path = f"/tmp/lattice_graphs/{run_id}.png"
    os.makedirs("/tmp/lattice_graphs", exist_ok=True)
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', pad_inches=0)
    plt.close()

    return FileResponse(png_path, media_type="image/png", filename=f"lattice_{run_id}.png")


def get_graph_png(run_id: str):
    import os
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx
    from fastapi.responses import FileResponse
    from osi.store import get_run, load_graph

    meta = get_run(run_id)
    if not meta:
        return {"error": "Run not found"}
    layer = (meta.get("config") or {}).get("layer")
    g = load_graph(run_id, layer) if layer else None
    if not g:
        return {"error": "Graph not found"}

    g_undir = g.to_undirected()
    largest_cc = max(nx.connected_components(g_undir), key=len)
    G = g.subgraph(largest_cc).copy()

    try:
        from pyforceatlas2 import ForceAtlas2
        fa2 = ForceAtlas2(
            outbound_attraction_distribution=False,
            edge_weight_influence=1.0,
            lin_log_mode=True,
            barnes_hut_optimize=True,
            scaling_ratio=20.0,
            strong_gravity_mode=True,
            gravity=20.0,
        )
        pos = fa2.forceatlas2_networkx_layout(G, pos=None, iterations=100)
    except Exception:
        pos = nx.spring_layout(G, seed=42)

    fig, ax = plt.subplots(figsize=(20, 20), facecolor='white')
    ax.set_facecolor('white')
    nx.draw_networkx_edges(G, pos, alpha=0.15, edge_color='gray', width=0.5, ax=ax)

    communities = list(nx.community.louvain_communities(G, seed=42))
    node_comm = {node: i for i, c in enumerate(communities) for node in c}
    PALETTE = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC"]
    node_colors = [PALETTE[node_comm.get(n, 0) % len(PALETTE)] for n in G.nodes()]
    node_sizes = [max(5, min(30, G.nodes[n].get("message_count", 1) * 2)) for n in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes, linewidths=0, ax=ax)
    ax.axis('off')

    png_path = f"/tmp/lattice_graphs/{run_id}.png"
    os.makedirs("/tmp/lattice_graphs", exist_ok=True)
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', pad_inches=0)
    plt.close()

    return FileResponse(png_path, media_type="image/png", filename=f"lattice_{run_id}.png")


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
    import networkx as nx
    import tempfile, os
    from fastapi.responses import FileResponse
    from osi.store import get_run, load_graph
    meta = get_run(run_id)
    if not meta: return {"error": "Run not found"}
    layer = (meta.get("config") or {}).get("layer")
    g = load_graph(run_id, layer) if layer else None
    if not g: return {"error": "Graph not found"}
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gexf")
    nx.write_gexf(g, tmp.name)
    return FileResponse(tmp.name, media_type="application/gexf+xml", filename=f"lattice_{run_id}.gexf")

@app.get("/api/export/md/{run_id}")
async def export_md(run_id: str):
    import networkx as nx
    from fastapi.responses import PlainTextResponse
    from osi.store import get_run, load_graph
    from osi.analysis import pagerank
    meta = get_run(run_id)
    if not meta: return {"error": "Run not found"}
    layer = (meta.get("config") or {}).get("layer")
    g = load_graph(run_id, layer) if layer else None
    if not g: return {"error": "Graph not found"}
    
    md = f"# Lattice Analysis: {run_id}\n\n"
    md += f"**Nodes:** {g.number_of_nodes()} | **Edges:** {g.number_of_edges()}\n\n"
    
    pr = pagerank(g)
    top_users = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:10]
    md += "## Top 10 Users by PageRank\n"
    for u, s in top_users:
        md += f"- **{u}**: {s:.4f}\n"
        
    md += "\n## Communities (Louvain)\n"
    comms = list(nx.community.louvain_communities(g, seed=42))
    for i, c in enumerate(comms[:5]):
        md += f"- **Group {i}**: {len(c)} members (e.g., {', '.join(list(c)[:3])}...)\n"
        
    return PlainTextResponse(md, media_type="text/markdown", headers={"Content-Disposition": f"attachment; filename=lattice_{run_id}.md"})
