import csv, os, re

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

GOV_KW = ("CITY OF","CITYOF","COUNTY OF","STATE OF","BOARD OF","SCHOOL DISTRICT",
          "VILLAGE OF","TOWNSHIP OF","UNITED STATES","U S A","U.S.A","CMHA","C.M.H.A.",
          "RTA","LIBRARY","METRO PARK","MET PK DIST","HOUSING AUTHORITY")
TRUSTEE_KW = re.compile(r"\bTRUSTEE\b|\bTRS\b|\(TRS\)|\(TRUSTEE\)|-TRUSTEE|CO-TRUSTEE")
ENTITY_KW = (" LLC","L.L.C","CORP","INC","LIMITED","L.P.","LLP"," L.P","COMPANY",
             "PARTNERSHIP","CHURCH","FOUNDATION","ASSOCIATION","HOA","CLINIC","SOCIETY",
             "UNIVERSITY","COLLEGE","FUND","REALTY","PROPERTIES","HOLDINGS","GROUP",
             "BANK","TRUST CO","MINISTRIES","DIOCESE","SCHOOL","ACADEMY","ESTATES MHC")
PLACEHOLDER = ("SEE PARCEL","VACANT","NONE","UNKNOWN","N/A","","TBD")
SINGLE_TOKEN_GOV = {"U.S.A","USA","CMHA","C.M.H.A.","LB","NHI"}

def label(shape, name):
    n = _u(name)
    if n in PLACEHOLDER or n.startswith("SEE PARCEL"): return "placeholder"
    if n in SINGLE_TOKEN_GOV: return "government"
    if any(k in n for k in GOV_KW): return "government"
    if TRUSTEE_KW.search(n) and " LLC" not in n and "CORP" not in n and "TRUST CO" not in n:
        return "trust"
    if any(k in n for k in ENTITY_KW): return "entity"
    if shape in ("single_token",) and len(n) <= 4: return "unclear"
    if shape in ("person_comma","person_joint","person_amp","person_etal"): return "person"
    if shape == "person_nocomma":
        toks = n.split()
        if 2 <= len(toks) <= 4: return "person"
        return "unclear"
    return "unclear"

inp = os.path.expanduser("~/Desktop/classifier_testset.tsv")
outp = os.path.expanduser("~/Desktop/classifier_testset.csv")
rows = list(csv.reader(open(inp), delimiter="\t"))
with open(outp, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["idx","shape","name","auto_label","final_label"])
    for r in rows[1:]:
        if len(r) < 3: continue
        idx, shape, name = r[0], r[1], r[2]
        al = label(shape, name)
        w.writerow([idx, shape, name, al, al])
print(f"wrote {outp}")
from collections import Counter
al = Counter(label(r[1], r[2]) for r in rows[1:] if len(r) >= 3)
print("auto-label distribution:")
for k, v in al.most_common(): print(f"  {k:12s} {v}")
