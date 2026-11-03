import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

_CACHE = None
_OWN_COUNTS = None

def load():
    global _CACHE, _OWN_COUNTS
    if _CACHE is None:
        _CACHE = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
        _OWN_COUNTS = []
        for n in _CACHE.nodes:
            if not n.startswith("owner|"): continue
            c = sum(1 for p in _CACHE.neighbors(n) if _CACHE.nodes[p].get("type") == "parcel")
            _OWN_COUNTS.append((n, c))
        _OWN_COUNTS.sort(key=lambda x: -x[1])
    return _CACHE


_SUITE_TOKENS = ("STE ", "SUITE", "PMB", "UNIT ", "#")

def _mail_class(G, addr_node):
    owners = [x for x in G.neighbors(addr_node) if x.startswith("owner|")]
    n = len(owners)
    if n == 2:
        import difflib
        a, b = [x[6:] for x in owners]
        ratio = difflib.SequenceMatcher(None, a.upper(), b.upper()).ratio()
        return "same_name_variant" if ratio > 0.85 else "trivial"
    if n < 2: return "trivial"
    kinds = [G.nodes[o].get("kind", "unknown") for o in owners]
    np = sum(1 for k in kinds if k == "person")
    ne = sum(1 for k in kinds if k == "entity")
    street = (G.nodes[addr_node].get("street") or "").upper()
    has_suite = any(t in street for t in _SUITE_TOKENS)
    if n >= 20:
        if has_suite or ne / n >= 0.7: return "commercial_drop"
        if np / n >= 0.7: return "residential_building"
        return "large_mixed"
    if n >= 11: return "mid_mixed"
    if np / n >= 0.7: return "small_household"
    if ne / n >= 0.7: return "small_entity"
    return "small_mixed"


def find_person(query):
    G = load()
    q = _u(query)
    exact_key = f"owner|{q}"
    if exact_key in G:
        return _dossier(exact_key)
    q_norm = re.sub(r"[^A-Z0-9 ]", " ", q).strip()
    q_norm = re.sub(r"\s+", " ", q_norm)
    exact = []
    fuzzy = []
    for n, d in G.nodes(data=True):
        if not n.startswith("owner|"): continue
        n_norm = re.sub(r"[^A-Z0-9 ]", " ", _u(n[6:])).strip()
        n_norm = re.sub(r"\s+", " ", n_norm)
        ps = [p for p in G.neighbors(n) if G.nodes[p].get("type") == "parcel"]
        if not ps: continue
        if n_norm == q_norm:
            exact.append((n, len(ps)))
        elif q_norm in n_norm:
            fuzzy.append((n, len(ps)))
    if len(exact) == 1:
        return _dossier(exact[0][0])
    matches = exact + fuzzy
    matches.sort(key=lambda x: -x[1])
    if not matches:
        return {"error": f"no owner found matching '{query}'"}
    if len(matches) == 1:
        return _dossier(matches[0][0])
    top = matches[0]
    return {
        "ambiguous": True,
        "biggest_match": {"name": top[0][6:], "parcels": top[1]},
        "candidates": [{"name": n[6:], "parcels": c} for n, c in matches[:10]],
        "note": f"multiple matches; largest is '{top[0][6:]}' with {top[1]} parcels",
    }


def _dossier(node_key):
    G = load()
    d = G.nodes[node_key]
    name = node_key[6:]
    parcels = [p for p in G.neighbors(node_key) if G.nodes[p].get("type") == "parcel"]
    addrs = [a for a in G.neighbors(node_key) if G.nodes[a].get("type") == "address"]

    zips = Counter()
    classes = Counter()
    total_value = 0.0
    for p in parcels:
        pd = G.nodes[p]
        z = pd.get("situs_zip") or pd.get("parcel_zip") or ""
        if not z:
            situs = pd.get("situs") or pd.get("situs_addr") or ""
            parts = situs.rsplit(",", 1)
            if len(parts) == 2: z = parts[-1].strip()
        if z: zips[z] += 1
        classes[pd.get("pclass") or pd.get("property_class") or "?"] += 1
        for k in ("value", "tax_market_total", "total_value"):
            v = pd.get(k)
            if v is not None:
                try: total_value += float(v); break
                except (TypeError, ValueError): pass

    co_owners = []
    transfers_out = []
    transfers_in = []
    suppressed = 0
    for nb in G.neighbors(node_key):
        if not nb.startswith("owner|"): continue
        e = G[node_key][nb]
        rel = e.get("relation", "?")
        if rel == "same_mail":
            shared = [a for a in G.neighbors(node_key) if a.startswith("mail|") and G.has_edge(nb, a)]
            cls = _mail_class(G, shared[0]) if shared else "unknown"
            if cls in ("residential_building", "commercial_drop", "large_mixed"):
                suppressed += 1
            else:
                co_owners.append((nb[6:], cls))
        elif rel == "sold_to":
            transfers_out.append((nb[6:], e.get("tx_weight", 0)))

    rank = next((i + 1 for i, (n, _c) in enumerate(_OWN_COUNTS) if n == node_key), None)
    total_owners = len(_OWN_COUNTS)

    limits = []
    if co_owners or suppressed:
        from collections import Counter as _C
        by_class = _C(cls for _, cls in co_owners)
        if suppressed: by_class["suppressed (building/drop)"] += suppressed
        parts = [f"{n} {c}" for c, n in by_class.most_common()]
        limits.insert(0, "Co-mailers: " + ", ".join(parts) + ". Small-entity clusters are candidates, not confirmed connections.")
    if transfers_out and not transfers_in:
        limits.append(
            f"{len(transfers_out)} outbound transfer(s) visible, no inbound. "
            "This owner's acquisition chain is not in the transfer graph; "
            "rank reflects current holdings only."
        )
    if len(addrs) > 1:
        zips_set = {G.nodes[a].get("zip") for a in addrs if G.nodes[a].get("zip")}
        if len(zips_set) > 1:
            limits.append(
                f"Mailing addresses span {len(zips_set)} ZIP(s). Whether a single "
                "party operates across these locations is untested."
            )
    if d.get("kind") == "person" and len(parcels) > 20:
        limits.append(
            f"{len(parcels)} parcels attributed to a single person string. "
            "Whether this is one individual or a same-name cluster is untested."
        )
    if d.get("kind") == "unknown":
        limits.append(
            "The classifier could not assign this owner a type. Treat kind as unknown."
        )
    limits.extend([
        "Beneficial ownership (who is behind this name): requires deed signatures or Delaware filings",
        "Political donations: not loaded",
        "Court records, code violations, evictions: not loaded",
        "Whether this name is a nominee for another party: untested",
    ])

    return {
        "name": name,
        "kind": d.get("kind", "unknown"),
        "total_parcels": len(parcels),
        "rank_among_owners": f"#{rank} of {total_owners:,}" if rank else "n/a",
        "total_assessed_value": total_value,
        "property_classes": dict(classes),
        "top_zips": zips.most_common(5),
        "mailing_addresses": [
            (G.nodes[a].get("street", "") + ", " + G.nodes[a].get("zip", "")).strip(", ")
            for a in addrs
        ],
        "co_owners_same_mail": co_owners[:10],
        "co_owners_suppressed": suppressed,
        "transfers_out": transfers_out[:10],
        "what_i_cannot_answer": limits,
    }


def render(dossier):
    if "error" in dossier: return dossier["error"]
    if "ambiguous" in dossier:
        out = ["Multiple matches for query:"]
        for c in dossier["candidates"]:
            out.append(f"  {c['parcels']:>4}p  {c['name']}")
        out.append(f"\n{dossier['note']}")
        return "\n".join(out)
    out = []
    out.append(f"{dossier['name']}  [{dossier['kind']}]")
    out.append("=" * 60)
    out.append(f"  parcels: {dossier['total_parcels']}")
    out.append(f"  rank:    {dossier['rank_among_owners']}")
    if dossier["total_assessed_value"]:
        out.append(f"  value:   ${dossier['total_assessed_value']:,.0f}")
    if dossier["property_classes"]:
        out.append(f"  classes: {dossier['property_classes']}")
    if dossier["top_zips"]:
        out.append("  top ZIPs:")
        for z, c in dossier["top_zips"]:
            out.append(f"    {c:>3}p in {z}")
    if dossier["mailing_addresses"]:
        out.append("  mailing:")
        for a in dossier["mailing_addresses"][:3]:
            out.append(f"    {a}")
    if dossier["co_owners_same_mail"]:
        out.append("  shares mail with:")
        for nm, rel in dossier["co_owners_same_mail"][:5]:
            out.append(f"    {nm[:50]}  ({rel})")
    if dossier.get("co_owners_suppressed"):
        out.append(f"    ({dossier[chr(39)+chr(99)+chr(111)+chr(95)+chr(111)+chr(119)+chr(110)+chr(101)+chr(114)+chr(115)+chr(95)+chr(115)+chr(117)+chr(112)+chr(112)+chr(114)+chr(101)+chr(115)+chr(115)+chr(101)+chr(100)+chr(39)]} additional co-mailers at building/drop addresses, suppressed)")
    if dossier["transfers_out"]:
        out.append("  sold to:")
        for nm, w in dossier["transfers_out"][:5]:
            out.append(f"    {w}p -> {nm[:50]}")
    out.append("")
    out.append("  what this graph CANNOT tell you:")
    for w in dossier["what_i_cannot_answer"]:
        out.append(f"    - {w}")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:])
    print(render(find_person(q)))



def render_ego(dossier, out_path=None):
    """Render the 1-hop ego graph for a dossier. Saves PNG, returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx

    if "error" in dossier or "ambiguous" in dossier:
        return None
    G = load()
    name = dossier["name"]
    center = f"owner|{name.upper()}"
    if center not in G:
        # try to find by substring
        for n in G.nodes:
            if n.startswith("owner|") and name.upper() in n.upper():
                center = n; break
        else:
            return None

    # 1-hop subgraph: owner + direct neighbors
    neighbors = list(G.neighbors(center))
    sub = G.subgraph([center] + neighbors).copy()

    if out_path is None:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", name)[:40]
        out_path = os.path.expanduser(f"~/Desktop/ego_{safe}.png")

    # color by node type
    colors = []
    sizes = []
    for n in sub.nodes():
        if n == center:
            colors.append("#e63946"); sizes.append(900)
        elif n.startswith("parcel|"):
            colors.append("#a8dadc"); sizes.append(80)
        elif n.startswith("mail|"):
            colors.append("#f4a261"); sizes.append(200)
        elif n.startswith("owner|"):
            colors.append("#457b9d"); sizes.append(300)
        else:
            colors.append("#cccccc"); sizes.append(100)

    pos = nx.spring_layout(sub, seed=42, k=0.6)
    fig, ax = plt.subplots(figsize=(12, 12))
    nx.draw_networkx_edges(sub, pos, ax=ax, alpha=0.15, width=0.5)
    nx.draw_networkx_nodes(sub, pos, ax=ax, node_color=colors, node_size=sizes, alpha=0.9)
    # label the center and any co-owners, not every parcel
    label_nodes = {n: n.split("|",1)[1][:25] for n in sub.nodes()
                   if n == center or n.startswith("owner|")}
    nx.draw_networkx_labels(sub, pos, labels=label_nodes, ax=ax, font_size=7)
    ax.set_title(f"Ego graph: {name}  ({len(neighbors)} neighbors)", fontsize=11)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
