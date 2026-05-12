"""
Script 102: OH graduation rates for high schools that have an IRN map.
Parses oh_building_grad_2023-24.xlsx (Graduation_Component sheet).
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"


def safe_float(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s in {"*","N/A","NA","NC","NULL","<10",".","-","PS","NR"}: return None
    try: return float(s)
    except: return None


# Hand-curated mapping of HS NCES IDs -> Ohio Building IRN
OH_HS = {
    "390004002939": "133629",  # Cleveland HS
    "390004202978": "133660",  # Columbus HS Morse Road (shares IRN with Columbus campus)
    "390136605556": "011534",  # Dayton HS
}


def main() -> None:
    print("\n=== OHIO graduation ===")
    path = RAW / "OH" / "_csv_grad" / "Graduation_Component.csv"
    if not path.exists():
        print("  File missing"); return
    by_irn = {}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            by_irn[r["Building IRN"].strip()] = r

    for nces_id, irn in OH_HS.items():
        r = by_irn.get(irn)
        if not r:
            print(f"  {nces_id} IRN={irn}: not found"); continue
        rec = json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())
        rec["graduation"]["year"] = YEAR
        four = safe_float(r.get("Four Year Graduation Rate - Class of 2023"))
        five = safe_float(r.get("Five Year Graduation Rate - Class of 2022"))
        rec["graduation"]["four_year_grad_rate"] = four
        rec["graduation"]["five_year_grad_rate"] = five
        # Also store the Graduation Rate Component star rating in accountability if not already set
        star = (r.get("Graduation Rate Component Rating") or "").strip()
        if star:
            star = " ".join(star.split())
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(rec, indent=2))
        print(f"  {nces_id} {rec['meta']['school_name'][:50]:50}  4yr={four}  5yr={five}  GradRating={star}")


if __name__ == "__main__":
    main()
