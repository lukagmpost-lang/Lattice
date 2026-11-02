import json, os, time, urllib.parse, urllib.request
BASE = "https://gis.cuyahogacounty.gov/server/rest/services/CCFO/Parcel_Fabric_Taxparcels/FeatureServer/0/query"
UA = {"User-Agent": "cuyahoga-transfer/1.0"}
WHERE = "grantor IS NOT NULL AND grantor <> '' AND grantee IS NOT NULL AND grantee <> ''"
FIELDS = "parcel_id,grantor,grantee,last_transfer_date,last_sales_amount,book_page,parcel_owner,property_class"
OUT = os.path.expanduser("~/Desktop/cuyahoga_transfers_raw.json")
def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())
total = get(BASE + "?" + urllib.parse.urlencode({"where": WHERE, "returnCountOnly": "true", "f": "json"}))["count"]
print(f"total: {total}")
rows, offset = [], 0
while offset < total:
    params = {"where": WHERE, "outFields": FIELDS, "returnGeometry": "false",
              "resultOffset": offset, "resultRecordCount": 5000, "f": "json"}
    d = get(BASE + "?" + urllib.parse.urlencode(params))
    feats = d.get("features", [])
    if not feats: break
    rows.extend([f["attributes"] for f in feats])
    offset += len(feats)
    print(f"  {offset}/{total}")
with open(OUT, "w") as fh:
    json.dump({"features": [{"attributes": r} for r in rows]}, fh)
print(f"wrote {OUT}: {len(rows)} rows")
