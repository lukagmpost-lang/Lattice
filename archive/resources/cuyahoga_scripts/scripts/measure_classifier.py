import csv, os, re
from collections import Counter, defaultdict

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

rows = list(csv.DictReader(open(os.path.expanduser("~/Desktop/classifier_testset.csv"))))
print(f"loaded {len(rows)} labeled names")

TRUSTEE_RE = re.compile(r"\(TRS\)|\(TRUSTEE\)|- ?TRUSTEE|CO-?TRUSTEE|\bTRUSTEE\b|\bSUC-?TRS\b")
PLACEHOLDER = {"VACANT LOT","VACANT LAND","SEE PARCEL","NONE","UNKNOWN","NULL","","TBD","UNKNOWN OWNER"}
GOV_PREFIX = ("CITY OF","CITY ","VILLAGE OF","STATE OF","COUNTY OF","TOWNSHIP OF",
              "BOARD OF","UNITED STATES","U S A","SECRETARY OF","DEPARTMENT OF","DISTRICT OF")
ENTITY_SUBSTR = (
    " LLC"," L.L.C"," CORP"," INC"," INCORPORATED"," L.P"," LLP","LTD"," LIMITED",
    " COMPANY"," CO."," PARTNERSHIP"," PARTNERS"," HOLDINGS"," PROPERTIES",
    " REALTY"," DEVELOPMENT"," FUND"," BANK"," CREDIT UNION",
    " CHURCH"," DIOCESE"," BISHOP"," MINISTRIES"," HOSPITAL"," HEALTH"," CLINIC",
    " UNIVERSITY"," COLLEGE"," FOUNDATION"," SCHOOL"," LIBRARY"," ACADEMY",
    " AUTHORITY"," METRO"," PARK DIST"," HOUSING"," CONSERVANCY"," RTA",
    " HABITAT"," HUMANITY"," NEIGHBORHOOD"," CDC",
    " MHC"," MHP"," ASSN"," ASSOC"," TRUST CO",
    " HOMES"," ESTATES"," RESERVE"," CASE WESTERN"," LAND CO"," PARK ",
)
LAST_TOKEN_ENTITY = {"LP","LLC","LLP","LTD","CO","INC","CORP","PC","PLLC","TRUST","L.P.","L.L.C.","CDC"}

def classify(name):
    n = _u(name)
    for sfx in (" ET AL"," ET UX"," ET VIR"):
        if n.endswith(sfx): n = n[:-len(sfx)].strip()
    if not n: return "unknown"
    if n in PLACEHOLDER or n.startswith("SEE PARCEL"): return "placeholder"
    if TRUSTEE_RE.search(n): return "trust"
    if any(n.startswith(p) for p in GOV_PREFIX): return "government"
    if any(k in n for k in ENTITY_SUBSTR): return "entity"
    toks = n.split()
    if toks and toks[-1].strip(".,") in LAST_TOKEN_ENTITY: return "entity"
    if re.search(r",\s*CITY|\bCITY\b|\bLB\d+", n): return "entity"
    if "," in n:
        head = n.split(",",1)[0].strip()
        if head and re.match(r"^[A-Z][A-Z .'-]+$", head) and len(head.split()) <= 3:
            return "person"
    if 2 <= len(toks) <= 3 and all(len(t) >= 2 and re.match(r"^[A-Z][A-Z.'-]*$", t) for t in toks):
        return "person"
    return "unknown"

LABEL_MAP = {"person":"person","entity":"entity","trust":"trust",
             "government":"government","placeholder":"placeholder","unclear":"unclear","unknown":"unclear"}
CATS = ["person","entity","trust","government","placeholder","unclear"]

confusion = defaultdict(Counter)
errors = []
for r in rows:
    name = r["name"]
    true = LABEL_MAP.get(r["final_label"].strip().lower(), "unclear")
    pred = LABEL_MAP.get(classify(name), "unclear")
    confusion[true][pred] += 1
    if pred != true:
        errors.append((r["idx"], name, true, pred))

# Header without backslash
header = "true" + " / " + "pred"
print("\n=== CONFUSION MATRIX (rows=true, cols=predicted) ===")
print(header.ljust(14) + " ".join(c.rjust(10) for c in CATS))
for true_cat in CATS:
    row_vals = " ".join(str(confusion[true_cat].get(c, 0)).rjust(10) for c in CATS)
    print(true_cat.ljust(14) + row_vals)

print("\n=== PER-CATEGORY METRICS ===")
print("category".ljust(12) + "prec".rjust(8) + "recall".rjust(8) + "f1".rjust(8) + "support".rjust(10))
for cat in CATS:
    tp = confusion[cat].get(cat, 0)
    fp = sum(confusion[other].get(cat, 0) for other in CATS if other != cat)
    fn = sum(confusion[cat].get(other, 0) for other in CATS if other != cat)
    prec = tp/(tp+fp) if tp+fp > 0 else 0.0
    rec = tp/(tp+fn) if tp+fn > 0 else 0.0
    f1 = 2*prec*rec/(prec+rec) if prec+rec > 0 else 0.0
    support = tp + fn
    line = cat.ljust(12) + f"{prec:>8.3f}" + f"{rec:>8.3f}" + f"{f1:>8.3f}" + f"{support:>10d}"
    print(line)

n_total = sum(sum(c.values()) for c in confusion.values())
n_correct = sum(confusion[c].get(c, 0) for c in CATS)
print(f"\noverall accuracy: {n_correct}/{n_total} = {100*n_correct/n_total:.1f}%")

print(f"\n=== {len(errors)} MISCLASSIFICATIONS ===")
for idx, name, true, pred in errors[:40]:
    print("  [" + str(idx).rjust(3) + "] " + name[:60].ljust(60) + "  true=" + true.ljust(10) + " pred=" + pred)
if len(errors) > 40:
    print(f"  ... and {len(errors)-40} more")
