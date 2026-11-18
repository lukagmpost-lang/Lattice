"""Cuyahoga County parcel fabric loader.

Reads ArcGIS FeatureServer JSON (already downloaded) or a CSV export of the
same, produces a bipartite NetworkX graph. Node types: parcel, owner, address.
Edge types: owns, owns_from.

Bipartite by construction. Owner strings are normalized but not merged by
similarity. Excluded fields (measured coverage too low or misleading):
parentpin, condo_complex_id, lender, second_owner, parcel_type,
foreclosure_flag, cert_sold_flag.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

_SENTINELS = {"", " ", "NO LENDER", "NONE", "NULL", "N/A"}


def _norm(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def _upper(s):
    return _norm(s).upper()


def _null(s):
    n = _upper(s)
    return None if n in _SENTINELS else n


def _zip_str(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date_ms(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _owner_key(name):
    n = _upper(name)
    return f"owner|{n}" if n else None


def _mail_key(street, city, zip_):
    s, c, z = _upper(street), _upper(city), _upper(zip_)
    if not s or not c:
        return None
    return f"mail|{s}|{c}|{z}"


def _parcel_key(pid):
    p = _norm(pid)
    return f"parcel|{p}" if p else None


def _iter_rows(path):
    """Yield attribute dictionaries from an ArcGIS JSON or CSV export."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".json":
        with p.open(encoding="utf-8-sig") as handle:
            data = json.load(handle)
        for feature in data.get("features", []):
            yield feature.get("attributes", {})
        return
    if suffix == ".csv":
        # utf-8-sig strips the BOM that ArcGIS CSV exports put before the
        # first column name; without it every field is named "\ufeffparcel_id".
        with p.open(encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)
        return
    raise ValueError(f"unsupported input {p.suffix}; use .json or .csv")


def _rows(path):
    return list(_iter_rows(path))


def detect_cuyahoga_format(path):
    p = Path(path)
    if p.suffix.lower() not in {".json", ".csv"}:
        return "low"
    try:
        first = next(iter(_iter_rows(path)), None)
    except Exception:
        return "low"
    if not first:
        return "low"
    keys = set(first.keys())
    return "high" if {"parcel_id", "parcel_owner"} <= keys else "low"


def _situs(row) -> str:
    parts = [
        _norm(row.get("par_addr_all")),
        _norm(row.get("parcel_city")),
        _norm(row.get("parcel_state")) or "OH",
        _zip_str(row.get("parcel_zip")),
    ]
    return ", ".join(part for part in parts if part)


def load_cuyahoga_parcels(path, *, include_exempt=False):
    G = nx.Graph()
    kept = 0
    rows_read = 0
    for r in _iter_rows(path):
        rows_read += 1
        pid = _norm(r.get("parcel_id"))
        owner = _norm(r.get("parcel_owner"))
        if not pid or not owner:
            continue
        pclass = _upper(r.get("property_class"))
        if not include_exempt and pclass == "E":
            continue
        pk = _parcel_key(pid)
        ok = _owner_key(owner)
        if pk is None or ok is None:
            continue
        kept += 1
        market_value = _float(r.get("tax_market_total"))
        situs = _situs(r)

        G.add_node(
            pk,
            type="parcel",
            parcel_id=pid,
            parcelpin=_norm(r.get("parcelpin")),
            account=_norm(r.get("account")),
            property_class=pclass,
            property_class_desc=_norm(r.get("prop_class_desc")),
            tax_luc=_norm(r.get("tax_luc")),
            tax_luc_desc=_norm(r.get("tax_luc_description")),
            # ``situs`` and ``value`` are the canonical names used by the
            # downstream merge; keep the split fields for existing callers.
            situs=situs,
            value=market_value,
            situs_addr=_norm(r.get("par_addr_all")),
            situs_city=_norm(r.get("parcel_city")),
            situs_state=_norm(r.get("parcel_state")) or "OH",
            situs_zip=_zip_str(r.get("parcel_zip")),
            book_page=_norm(r.get("book_page")),
            last_transfer_date=_date_ms(r.get("last_transfer_date")),
            last_sales_amount=_float(r.get("last_sales_amount")),
            tax_market_total=market_value,
            tax_assessed_total=_float(r.get("tax_assessed_total")),
            lender=_null(r.get("lender")),
        )

        G.add_node(
            ok,
            type="owner",
            name=_norm(r.get("parcel_owner")),
            mail_name=_norm(r.get("mail_name")),
        )

        weight = market_value or 1.0
        G.add_edge(ok, pk, relation="owns", weight=weight)

        mk = _mail_key(r.get("mail_addr_street"), r.get("mail_city"), r.get("mail_zip"))
        if mk:
            G.add_node(
                mk,
                type="address",
                street=_upper(r.get("mail_addr_street")),
                city=_upper(r.get("mail_city")),
                state=_upper(r.get("mail_state")),
                zip=_zip_str(r.get("mail_zip")),
            )
            G.add_edge(ok, mk, relation="owns_from")

    meta = {
        "source": "cuyahoga",
        "rows_read": rows_read,
        "rows_kept": kept,
        "n_nodes": G.number_of_nodes(),
        "n_edges": G.number_of_edges(),
        "n_owner_nodes": sum(1 for _, d in G.nodes(data=True) if d.get("type") == "owner"),
        "n_parcel_nodes": sum(1 for _, d in G.nodes(data=True) if d.get("type") == "parcel"),
        "n_address_nodes": sum(1 for _, d in G.nodes(data=True) if d.get("type") == "address"),
    }
    return G, meta


def project_owners(G):
    """Two-hop projection: owners linked by shared mailing address or shared parcel."""
    H = nx.Graph()
    for n, d in G.nodes(data=True):
        if d.get("type") == "owner":
            H.add_node(n, **d)

    def _add(u, v, kind, node_id):
        if H.has_edge(u, v):
            H[u][v].setdefault(kind, set()).add(node_id)
        else:
            H.add_edge(u, v, **{kind: {node_id}})

    for n, d in G.nodes(data=True):
        t = d.get("type")
        if t not in ("address", "parcel"):
            continue
        owners = [u for u in G.neighbors(n) if G.nodes[u].get("type") == "owner"]
        kind = "shared_addresses" if t == "address" else "shared_parcels"
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                _add(owners[i], owners[j], kind, n)

    for u, v, d in H.edges(data=True):
        relations = []
        for kind in ("shared_addresses", "shared_parcels"):
            if kind in d:
                d[f"n_{kind}"] = len(d[kind])
                d[kind] = sorted(d[kind])
        if "shared_addresses" in d:
            relations.append("same_mail")
        if "shared_parcels" in d:
            relations.append("co_owner")
        d["relation"] = " | ".join(relations) or "related"
    return H
