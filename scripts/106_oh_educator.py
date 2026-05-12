"""
Script 106: Populate OH teacher quality from oh_educator_data_2023-24.xlsx.

Fields populated:
- staff.teacher_fte: Number of Full Time Teachers (FTE) — overrides NCES CCD
- staff.pct_teachers_novice: Percent of Teachers Inexperienced
- staff.pct_teachers_certified: 100 - Percent Teachers on Temporary/Conditional Credentials
  (i.e., fraction of teachers on full credentials)
- staff.year: "2023-24"

Note: OH educator file doesn't expose teacher retention rate.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"


def safe_float(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s in {"*","N/A","NA","NC","NULL","<10",".","-","NR","PS"}: return None
    try: return float(s)
    except: return None


# Same NCES -> IRN map as OH proficiency
OH_NCES_TO_IRN = {
    "390045105010": "000825", "390051005220": "000338", "390004002939": "133629",
    "390047005029": "000858", "390045405013": "000838", "390136505544": "011533",
    "390138905567": "011986", "390004202978": "133660", "390132205440": "009179",
    "390160605963": "133660", "390135305483": "133660", "390064505319": "008280",
    "390044405003": "000808", "390136605556": "011534", "390138305625": "011976",
    "390044105000": "000804",
    # Noble Academy Euclid IRN missing
}


def main() -> None:
    print("=== OHIO educator data ===")
    csv_path = RAW / "OH" / "_csv" / "oh_educator_2023-24.csv"
    if not csv_path.exists():
        print("  File missing"); return
    by_irn = {}
    with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            by_irn[r["Building IRN"].strip()] = r

    for nces_id, irn in OH_NCES_TO_IRN.items():
        r = by_irn.get(irn)
        if not r:
            print(f"  {nces_id} IRN={irn}: not in educator file"); continue
        rec = json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())
        rec["staff"]["year"] = YEAR

        fte = safe_float(r.get("Number of Full Time Teachers (FTE)"))
        novice = safe_float(r.get("Percent of Teachers Inexperienced"))
        temp_cred = safe_float(r.get("Percent Teachers on Temporary/Conditional Credentials"))
        if fte is not None:
            rec["staff"]["teacher_fte"] = fte
        if novice is not None:
            rec["staff"]["pct_teachers_novice"] = novice
        if temp_cred is not None:
            rec["staff"]["pct_teachers_certified"] = round(100 - temp_cred, 1)

        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(rec, indent=2))
        cert = rec["staff"]["pct_teachers_certified"]
        print(f"  {nces_id} {rec['meta']['school_name'][:42]:42}  FTE={fte}  Novice%={novice}  Cert%={cert}")


if __name__ == "__main__":
    main()
