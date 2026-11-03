import os, pickle, re, random
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

# Collect every owner string
owners = [n[6:] for n in G.nodes if n.startswith("owner|")]
print(f"total owner strings: {len(owners):,}")

# Stratify by name shape
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

strat = Counter(shape(o) for o in owners)
print(f"\nshape distribution:")
for k, v in strat.most_common():
    print(f"  {k:20s} {v:>6,}")

# Sample 300, proportional to shape, cap at 40 per shape
random.seed(42)
by_shape = {}
for o in owners:
    by_shape.setdefault(shape(o), []).append(o)

sample = []
for s, names in by_shape.items():
    n = min(40, max(10, int(300 * len(names) / len(owners))))
    sample.extend([(s, x) for x in random.sample(names, min(n, len(names)))])

# Trim to exactly 300 if over
if len(sample) > 300:
    random.shuffle(sample)
    sample = sample[:300]

print(f"\nsampling: {len(sample)} names across {len(set(s for s,_ in sample))} shapes")
sdist = Counter(s for s,_ in sample)
for k, v in sdist.most_common():
    print(f"  {k:20s} {v:>3d}")

out = os.path.expanduser("~/Desktop/classifier_testset.tsv")
with open(out, "w") as fh:
    fh.write("idx\tpredicted_shape\tname\tlabel\n")
    for i, (s, name) in enumerate(sample, 1):
        fh.write(f"{i}\t{s}\t{name}\t\n")
print(f"\nwrote {out}")
print(f"\nNext: open in Numbers, fill 'label' column with one of:")
print(f"  person, entity, trust, government, placeholder, unclear")
print(f"\nAim for a single sitting; the frozen set is the reference for all future classifier changes.")
