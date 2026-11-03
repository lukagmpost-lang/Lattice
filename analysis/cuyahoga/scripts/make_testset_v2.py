import os, pickle, re, random
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
owners = [n[6:] for n in G.nodes if n.startswith("owner|")]

def shape(name):
    n = _u(name)
    has_comma = "," in n
    has_entity = any(k in n for k in ["LLC","CORP","INC","LP","LLP","LTD","TRUST","CO.","COMPANY","PARTNERSHIP"])
    has_gov = any(k in n for k in ["CITY","COUNTY","STATE","DISTRICT","AUTHORITY","BOARD","VILLAGE"])
    has_trustee = "TRUSTEE" in n or "TRS" in n or "SUC-TRS" in n
    has_amp = "&" in n
    has_et_al = "ET AL" in n
    tokens = n.split()
    if has_gov: return "government"
    if has_trustee: return "trustee"
    if has_entity: return "entity"
    if has_comma and has_amp: return "person_joint"
    if has_comma: return "person_comma"
    if has_amp: return "person_amp"
    if has_et_al: return "person_etal"
    if len(tokens) >= 2: return "person_nocomma"
    return "single_token"

by_shape = {}
for o in owners:
    by_shape.setdefault(shape(o), []).append(o)

# WEIGHTED: over-sample hard shapes
WEIGHTS = {
    "trustee":         50,
    "person_amp":      30,
    "person_nocomma":  40,
    "single_token":    20,
    "person_etal":     20,
    "entity":          40,
    "government":      20,
    "person_joint":    30,
    "person_comma":    30,
}

random.seed(43)
sample = []
for s, names in by_shape.items():
    n = WEIGHTS.get(s, 20)
    n = min(n, len(names))
    sample.extend([(s, x) for x in random.sample(names, n)])

# Add known-hard cases from the audit if present in graph
KNOWN_HARD = [
    "ALVA, MARIA (TRUSTEE)",
    "NOURI, ALI & GERI- CO TRUSTEES",
    "MCGUIRE, LINDA J.- TRUSTEE",
    "ISSENMANN CLARENCE",
    "MUNIZ RICARDO",
    "PARMA ESTATES MHC",
    "CLEVELAND CLINIC HEALTH SYSTEM EAST REGION ETAL",
    "VILLAGE OF MAYFIELD",
    "CITY OF CLEVELAND",
    "YELDER HORACE & ROSE",
    "THE MOST REVEREND EDWARD C. MALESIC",
    "HENRIETTA HOMES CLEVELAND, L.P.",
]
present_hard = [h for h in KNOWN_HARD if any(_u(o) == _u(h) for o in owners)]
existing = set(_u(n) for _, n in sample)
for h in present_hard:
    if _u(h) not in existing:
        sample.append(("hard", h))

print(f"total sample: {len(sample)}")
sdist = Counter(s for s,_ in sample)
for k, v in sdist.most_common():
    print(f"  {k:20s} {v:>3d}")

out = os.path.expanduser("~/Desktop/classifier_testset.tsv")
with open(out, "w") as fh:
    fh.write("idx\tpredicted_shape\tname\tlabel\n")
    for i, (s, name) in enumerate(sample, 1):
        fh.write(f"{i}\t{s}\t{name}\t\n")
print(f"\nwrote {out}")
print(f"label options: person, entity, trust, government, placeholder, unclear")
