import json, os, re
from collections import defaultdict, Counter
from datetime import datetime, timezone

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

raw = [f["attributes"] for f in json.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers_raw.json")))["features"]]

LB_KW = ("LAND REUTILIZATION","LAND REUTILZATION","LAND REUTLIZATION",
         "LAND RETULIZATION","LAND TEUTILIZATION","L/B")
def is_lb(name): return any(k in _u(name) for k in LB_KW)

# Build acquisition events: (parcel_id, acquisition_date, owner_name)
# Acquisition = grantee is LB, grantor is not LB (external acquisition)
# Internal transfers (LB->LB) are not true acquisitions
acquired = {}
for r in raw:
    pid = str(r.get("parcel_id") or "").strip()
    if not pid: continue
    g_lb = is_lb(r.get("grantor"))
    t_lb = is_lb(r.get("grantee"))
    if t_lb and not g_lb:
        # external acquisition
        ms = r.get("last_transfer_date")
        if not ms: continue
        try:
            dt = datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if pid not in acquired or dt < acquired[pid]["date"]:
            acquired[pid] = {"date": dt, "grantee": r.get("grantee")}

# Build release events: grantor is LB, grantee is not LB
released_at = {}
for r in raw:
    pid = str(r.get("parcel_id") or "").strip()
    if not pid: continue
    if is_lb(r.get("grantor")) and not is_lb(r.get("grantee")):
        ms = r.get("last_transfer_date")
        if not ms: continue
        try:
            dt = datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if pid not in released_at or dt < released_at[pid]:
            released_at[pid] = dt

print(f"parcels with external LB acquisition event: {len(acquired):,}")
print(f"parcels with LB release event:              {len(released_at):,}")

NOW = datetime.now(timezone.utc)
print("\n=== COHORT RELEASE RATE ===")
print(f"{'acquired':>10s}  {'n':>6s}  {'released':>9s}  {'rate':>6s}")
for years in (1, 2, 3, 5, 7, 10):
    cutoff = NOW.replace(year=NOW.year - years)
    cohort = {pid: d for pid, d in acquired.items() if d["date"] <= cutoff}
    if not cohort: continue
    released = sum(1 for pid in cohort if pid in released_at and released_at[pid] >= cohort[pid]["date"])
    print(f"{years:>8d}y  {len(cohort):>6,}  {released:>9,}  {100*released/max(1,len(cohort)):>5.1f}%")

# Distinguish same-period held vs released
print("\n=== HOLDING PATTERN (parcels acquired, what happened next) ===")
held_still = 0
released_any = 0
for pid, d in acquired.items():
    if pid in released_at and released_at[pid] >= d["date"]:
        released_any += 1
    else:
        held_still += 1
print(f"  parcels acquired from external LB event: {len(acquired):,}")
print(f"  of those, released at some point after:   {released_any:,} ({100*released_any/max(1,len(acquired)):.1f}%)")
print(f"  of those, never released:                 {held_still:,} ({100*held_still/max(1,len(acquired)):.1f}%)")
