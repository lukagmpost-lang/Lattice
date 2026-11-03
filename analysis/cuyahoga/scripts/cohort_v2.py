import json, os, re
from collections import defaultdict
from datetime import datetime, timezone

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()
raw = [f["attributes"] for f in json.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers_raw.json")))["features"]]

LB_KW = ("LAND REUTILIZATION","LAND REUTILZATION","LAND REUTLIZATION",
         "LAND RETULIZATION","LAND TEUTILIZATION","L/B")
def is_lb(name): return any(k in _u(name) for k in LB_KW)

def to_dt(ms):
    try: return datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError): return None

# For each parcel, find its most recent LB-related event
# The "last_transfer_date" is the date of the LAST transfer. If it's the
# land bank releasing to X, that's the release event. If it's the land bank
# acquiring from Y, that's the acquisition event. But one row per parcel
# means we only have the LAST event, not both.

# Rebuild from raw by classifying last event
lb_acq = defaultdict(list)      # parcel -> [(date, grantor, grantee)]
lb_release = defaultdict(list)

for r in raw:
    pid = str(r.get("parcel_id") or "").strip()
    if not pid: continue
    d = to_dt(r.get("last_transfer_date"))
    if not d: continue
    g, t = _u(r.get("grantor")), _u(r.get("grantee"))
    g_lb, t_lb = is_lb(g), is_lb(t)
    if t_lb and not g_lb:
        lb_acq[pid].append((d, g, t))
    elif g_lb and not t_lb:
        lb_release[pid].append((d, g, t))
    elif g_lb and t_lb:
        pass  # internal, ignore

print(f"parcels whose LAST transfer was INTO an LB (from non-LB): {len(lb_acq):,}")
print(f"parcels whose LAST transfer was OUT of an LB (to non-LB): {len(lb_release):,}")
print(f"parcels in both (acquired then released): {len(set(lb_acq) & set(lb_release)):,}")

# That last line is the answer. Since each parcel has ONE last transfer,
# a parcel can only be in lb_acq OR lb_release, never both. Which means:
# this dataset CANNOT measure release rate for parcels the LB currently holds,
# because their last transfer was the acquisition and the release hasn't
# happened yet (or happened outside the data).

print("\n=== WHAT WE CAN MEASURE ===")
print(f"Cumulative external acquisitions:  {len(lb_acq):,}")
print(f"Cumulative external releases:      {len(lb_release):,}")

# Now measure using GRANTOR as the LB identity, not parcel ID
print("\n=== ACQUISITION DATE DISTRIBUTION (lb_acq) ===")
year_dist = defaultdict(int)
for pid, events in lb_acq.items():
    for d, g, t in events:
        year_dist[d.year] += 1
for y in sorted(year_dist):
    bar = '#' * min(60, year_dist[y] // 20)
    print(f"  {y}: {year_dist[y]:>4d}  {bar}")

# Release date distribution
print("\n=== RELEASE DATE DISTRIBUTION (lb_release) ===")
rel_year = defaultdict(int)
for pid, events in lb_release.items():
    for d, g, t in events:
        rel_year[d.year] += 1
for y in sorted(rel_year):
    bar = '#' * min(60, rel_year[y] // 20)
    print(f"  {y}: {rel_year[y]:>4d}  {bar}")

# The real rate: of parcels whose last transfer was INTO an LB
# (i.e., LB currently holds them), what's the oldest? If those go back to 2010
# and they're still held, that's the honest "age of held inventory"
held_dates = [d for events in lb_acq.values() for d, g, t in events]
if held_dates:
    from collections import Counter
    held_years = Counter(d.year for d in held_dates)
    print(f"\n=== AGE OF HELD INVENTORY (parcels where LB is current owner) ===")
    print(f"  earliest: {min(held_dates).year}")
    print(f"  latest:   {max(held_dates).year}")
    print(f"  median:   {sorted(held_dates)[len(held_dates)//2].year}")
    old_holds = sum(1 for d in held_dates if (datetime.now(timezone.utc) - d).days > 5*365)
    print(f"  parcels held >5 years: {old_holds:,} ({100*old_holds/max(1,len(held_dates)):.1f}%)")
    ten_yr = sum(1 for d in held_dates if (datetime.now(timezone.utc) - d).days > 10*365)
    print(f"  parcels held >10 years: {ten_yr:,} ({100*ten_yr/max(1,len(held_dates)):.1f}%)")
