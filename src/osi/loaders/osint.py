from __future__ import annotations
import json, os, re, sys, time, urllib.request
from pathlib import Path

import networkx as nx

PIVOT_PLANNER = Path(os.environ.get(
    "PIVOT_PLANNER_DIR",
    str(Path.home() / "Desktop" / "OSI" / "pivot-planner")
))
if str(PIVOT_PLANNER) not in sys.path:
    sys.path.insert(0, str(PIVOT_PLANNER))

from collector import Graph, collect_wikidata, collect_littlesis
from scope_gate import check as scope_check
from expand_lib import expand_graph
from sibling_derive import derive_siblings

_QID_RE = re.compile(r"^Q\d+$")


def detect_osint_format(path):
    p = Path(path)
    if not p.is_file() or p.suffix.lower() != ".json":
        return "low"
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return "low"
    return "high" if isinstance(data, dict) and "query" in data else "low"


def _fetch_missing_labels(graph_dict):
    qid_to_nodes = {}
    for n in graph_dict["nodes"]:
        if _QID_RE.match(n.get("name", "")):
            qid_to_nodes.setdefault(n["name"], []).append(n)
    if not qid_to_nodes:
        return 0
    qids = list(qid_to_nodes.keys())
    updated = 0
    for i in range(0, len(qids), 50):
        batch = qids[i:i+50]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities"
               "&ids=" + "|".join(batch) + "&props=labels&languages=en&format=json")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "osi-loader/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
        except Exception:
            continue
        for qid, ent in data.get("entities", {}).items():
            label = ent.get("labels", {}).get("en", {}).get("value")
            if not label or qid not in qid_to_nodes:
                continue
            for n in qid_to_nodes[qid]:
                n["name"] = label
                updated += 1
        time.sleep(0.4)
    return updated


def _to_networkx(graph_dict):
    id_to_name = {}
    name_counts = {}
    for n in graph_dict["nodes"]:
        base = (n.get("name") or n["id"]).strip() or n["id"]
        name_counts[base] = name_counts.get(base, 0) + 1
        id_to_name[n["id"]] = base
    for nid, name in list(id_to_name.items()):
        if name_counts[name] > 1:
            id_to_name[nid] = name + " (" + nid.split(":")[-1] + ")"

    G = nx.Graph()
    for n in graph_dict["nodes"]:
        display = id_to_name[n["id"]]
        G.add_node(display, original_id=n["id"],
                   type=n.get("type", "unknown"),
                   aliases=list(n.get("aliases") or []))

    for e in graph_dict["edges"]:
        src = id_to_name.get(e["source"])
        tgt = id_to_name.get(e["target"])
        if not src or not tgt or src == tgt:
            continue
        rel = e.get("relation", "connected")
        inf = e.get("inferred", False)
        if G.has_edge(src, tgt):
            G[src][tgt]["weight"] += 1.0
            existing = G[src][tgt].get("relation", "")
            if rel not in existing.split(" | "):
                G[src][tgt]["relation"] = existing + " | " + rel if existing else rel
            G[src][tgt]["inferred"] = G[src][tgt].get("inferred", False) or inf
        else:
            G.add_edge(src, tgt, relation=rel, inferred=inf,
                       confidence=e.get("confidence", 1.0), weight=1.0)
    return G


def load_osint_entity(path, **options):
    cfg = json.loads(Path(path).read_text())
    query = cfg.get("query")
    if not query:
        raise ValueError(str(path) + " is missing 'query' field")

    sources = cfg.get("sources", ["wikidata", "littlesis"])
    depth = int(cfg.get("depth", 2))
    include_family = bool(cfg.get("include_family", True))

    allowed, reason, qid, attrs = scope_check(query)
    if not allowed:
        raise ValueError("scope gate rejected '" + query + "': " + reason)
    print("[osint] scope gate passed: qid=" + str(qid))

    g = Graph()
    for source in sources:
        if source == "wikidata":
            msg = collect_wikidata(g, query)
        elif source == "littlesis":
            msg = collect_littlesis(g, query)
        else:
            msg = source + ": unsupported in loader"
        print("[osint] " + msg)
    g.resolve()
    collected = g.to_dict(query)
    print("[osint] collected: " + str(collected["node_count"]) + " nodes, " + str(collected["edge_count"]) + " edges")

    if depth > 0 and qid:
        collected = expand_graph(collected, seed_qids=[qid], depth=depth, log=print)
        print("[osint] expanded: " + str(collected["node_count"]) + " nodes, " + str(collected["edge_count"]) + " edges")

    if include_family and depth > 0:
        added = derive_siblings(collected)
        if added:
            print("[osint] derived " + str(added) + " inferred sibling edges")

    labeled = _fetch_missing_labels(collected)
    if labeled:
        print("[osint] labeled " + str(labeled) + " wikidata nodes")

    G = _to_networkx(collected)
    print("[osint] graph: " + str(G.number_of_nodes()) + " nodes, " + str(G.number_of_edges()) + " edges")

    return G, {
        "source": "osint",
        "query": query,
        "query_type": cfg.get("query_type", "person"),
        "wikidata_qid": qid,
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "scope_gate_attrs": attrs,
    }
