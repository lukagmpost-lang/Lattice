import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

TRUSTEE_RE = re.compile(r"\(TRS\)?|\(TRUSTEE\)|CO-?TRS|CO-?TRUSTEE|- ?TRS\.?|- ?TRUSTEE|\bTRS\.?$|\bTRUSTEE\b|\bSUC-?TRS\b|\bTRS\.?\b")
PLACEHOLDER = {"VACANT LOT","VACANT LAND","SEE PARCEL","NONE","UNKNOWN","NULL","","TBD","UNKNOWN OWNER","N/A"}
GOV_PREFIX = (
    "CITY OF","CITY ","THE CITY OF","THE CITYOF","VILLAGE OF","THE VILLAGE OF",
    "TOWNSHIP OF","STATE OF","COUNTY OF","BOARD OF","THE BOARD OF",
    "UNITED STATES","U S A","SECRETARY OF","DEPARTMENT OF","DISTRICT OF",
    "LIBRARY","PUBLIC LIBRARY","CLEVELAND PUBLIC LIBRARY","METRO PARK","MET PK",
    "SCHOOL DISTRICT","SCHOOLS","RTA","CMHA","HOUSING AUTHORITY",
)
GOV_SUBSTR = (
    "SCHOOL DISTRICT","LIBRARY","METRO PARK","MET PK","PARK DIST","HOUSING AUTHORITY",
    "BOARD OF EDUCATION","BOARD OF PARK","PARMA CITY SCHOOL","CITY OF CLEVE",
    "CITYOF ","VILLAGE OF","TOWNSHIP OF","PORT AUTHORITY","TRANSIT AUTHORITY",
)
ENTITY_SUBSTR = (
    " LLC"," L.L.C"," CORP"," INC"," INCORPORATED"," L.P"," LLP","LTD"," LIMITED",
    " COMPANY"," CO."," PARTNERSHIP"," PARTNERS"," HOLDINGS"," PROPERTIES",
    " REALTY"," DEVELOPMENT"," FUND"," BANK"," CREDIT UNION",
    " CHURCH"," DIOCESE"," BISHOP"," MINISTRIES"," HOSPITAL"," HEALTH"," CLINIC",
    " UNIVERSITY"," COLLEGE"," FOUNDATION"," SCHOOL"," ACADEMY",
    " AUTHORITY"," METRO"," HOUSING"," CONSERVANCY",
    " HABITAT"," HUMANITY"," NEIGHBORHOOD"," CDC",
    " MHC"," MHP"," ASSN"," ASSOC"," TRUST CO"," ASSC",
    " HOMES"," ESTATES"," RESERVE"," CASE WESTERN"," LAND CO"," SOCIETY",
    " SOLUTIONS"," SERVICES"," CLUSTER HOUSING",
)
LAST_TOKEN_ENTITY = {"LP","LLC","LLP","LTD","CO","INC","CORP","PC","PLLC","TRUST","L.P.","L.L.C.","CDC","ASSC"}

def classify_v6(name):
    n = _u(name)
    for sfx in (" ET AL"," ET UX"," ET VIR"):
        if n.endswith(sfx): n = n[:-len(sfx)].strip()
    if not n: return "unknown"
    if n in PLACEHOLDER or n.startswith("SEE PARCEL"): return "placeholder"
    # Government first (highest value in catching these)
    if any(n.startswith(p) for p in GOV_PREFIX): return "government"
    if any(k in n for k in GOV_SUBSTR): return "government"
    # Entity before trustee — "NORTHERN TRUST CO TRUSTEE" is entity
    if any(k in n for k in ENTITY_SUBSTR): return "entity"
    toks = n.split()
    if toks and toks[-1].strip(".,") in LAST_TOKEN_ENTITY: return "entity"
    if re.search(r",\s*CITY|\bLB\d+", n): return "government"
    # Trustee check AFTER entity so LLC TRUSTEE becomes entity
    if TRUSTEE_RE.search(n): return "trust"
    # Person: comma form
    if "," in n:
        head = n.split(",",1)[0].strip()
        if head and re.match(r"^[A-Z][A-Z .'-]+$", head) and len(head.split()) <= 3:
            return "person"
    # Person: multi-token no-comma form (allow single-char initials at end)
    if 2 <= len(toks) <= 4:
        all_caps = all(re.match(r"^[A-Z][A-Z.'-]*$", t) for t in toks)
        initials_ok = all(len(t) >= 2 or i == len(toks)-1 for i, t in enumerate(toks))
        if all_caps and initials_ok:
            return "person"
    return "unknown"

# Test on frozen set
import csv
rows = list(csv.DictReader(open(os.path.expanduser("~/Desktop/classifier_testset.csv"))))
LABEL_MAP = {"person":"person","entity":"entity","trust":"trust","government":"government",
             "placeholder":"placeholder","unclear":"unclear","unknown":"unclear"}
CATS = ["person","entity","trust","government","placeholder","unclear"]

confusion = {}
for c in CATS: confusion[c] = Counter()
errors = []
for r in rows:
    true = LABEL_MAP.get(r["final_label"].strip().lower(), "unclear")
    pred = LABEL_MAP.get(classify_v6(r["name"]), "unclear")
    confusion[true][pred] += 1
    if pred != true: errors.append((r["idx"], r["name"], true, pred))

print("=== v6 CONFUSION MATRIX ===")
print("true / pred".ljust(14) + " ".join(c.rjust(10) for c in CATS))
for t in CATS:
    print(t.ljust(14) + " ".join(str(confusion[t].get(c,0)).rjust(10) for c in CATS))

print("\n=== v6 METRICS ===")
print("category".ljust(12) + "prec".rjust(8) + "recall".rjust(8) + "f1".rjust(8) + "support".rjust(10))
for cat in CATS:
    tp = confusion[cat].get(cat, 0)
    fp = sum(confusion[o].get(cat, 0) for o in CATS if o != cat)
    fn = sum(confusion[cat].get(o, 0) for o in CATS if o != cat)
    prec = tp/(tp+fp) if tp+fp > 0 else 0
    rec = tp/(tp+fn) if tp+fn > 0 else 0
    f1 = 2*prec*rec/(prec+rec) if prec+rec > 0 else 0
    print(cat.ljust(12) + f"{prec:>8.3f}" + f"{rec:>8.3f}" + f"{f1:>8.3f}" + f"{tp+fn:>10d}")

n = sum(sum(c.values()) for c in confusion.values())
correct = sum(confusion[c].get(c,0) for c in CATS)
print(f"\nv6 accuracy: {correct}/{n} = {100*correct/n:.1f}%")
print(f"v5 accuracy: 70.4%")
print(f"improvement: {100*correct/n - 70.4:+.1f} pp")

print(f"\n=== v6 {len(errors)} MISCLASSIFICATIONS ===")
for idx, name, true, pred in errors[:30]:
    print("  [" + str(idx).rjust(3) + "] " + name[:55].ljust(55) + " true=" + true.ljust(10) + " pred=" + pred)

# If v6 better, apply to graph
if correct/n > 0.80:
    print("\napplying v6 to unified graph...")
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    before = Counter(G.nodes[n].get("kind","?") for n in G.nodes if n.startswith("owner|"))
    for n in G.nodes:
        if n.startswith("owner|"):
            G.nodes[n]["kind"] = classify_v6(n[6:])
    after = Counter(G.nodes[n].get("kind","?") for n in G.nodes if n.startswith("owner|"))
    print("before:", dict(before))
    print("after: ", dict(after))
    pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
    print("saved unified pickle")
