"""
Script 113: Populate Iowa HSA Des Moines staff data from BEDS Staff File.

Source: ia_teacher_info_2023-24.csv
Row for "Horizon Science Academy" (district 8200, AEA 11):
  col 7  Number of FT Teachers/Teacher Leaders = 9
  col 9  Number of Other Teachers/Teacher Leaders = 0
  col 19 Number of Beginning FT Teachers = 2
  col 23 FT Teacher/Teacher Leader Avg Total Experience = 7.9 yrs
  col 28 Percent of FT Teachers w/ Advanced Degrees = 0.222

Iowa doesn't publish school-level cert % or year-over-year retention directly.
We fill: teacher_fte, pct_teachers_novice (beginning/total).
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"

NCES_HSA_DESMOINES = "199902002316"


def safe_float(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s in {"*","N/A","NA","NULL","<10",".","-"}: return None
    try: return float(s)
    except: return None


def main():
    print("=== IA HSA Des Moines staff ===")
    path = RAW / "IA" / "ia_teacher_info_2023-24.csv"
    if not path.exists():
        print("  File missing"); return

    target_row = None
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 30: continue
            # District name appears in col 3
            name = (row[3] or "").strip()
            if name.lower() == "horizon science academy":
                target_row = row
                break

    if not target_row:
        print("  HSA Des Moines row not found"); return

    ft = safe_float(target_row[6])
    beginning = safe_float(target_row[19])

    novice_pct = round(beginning / ft * 100, 1) if (ft and beginning is not None and ft > 0) else None

    rec = json.loads((BY_SCHOOL / f"{NCES_HSA_DESMOINES}.json").read_text())
    rec["staff"]["year"] = YEAR
    rec["staff"]["teacher_fte"] = ft
    if novice_pct is not None:
        rec["staff"]["pct_teachers_novice"] = novice_pct
    rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL / f"{NCES_HSA_DESMOINES}.json").write_text(json.dumps(rec, indent=2))

    print(f"  FT teachers: {ft}")
    print(f"  Beginning teachers: {beginning}")
    print(f"  Novice rate: {novice_pct}%")
    print(f"  Updated: {NCES_HSA_DESMOINES} HSA Des Moines")


if __name__ == "__main__":
    main()
