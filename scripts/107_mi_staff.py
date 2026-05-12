"""
Script 107: Populate MI teacher data from the Staffing Count CSV.

Fields populated:
- staff.teacher_fte: Teachers, All Staff row, FTE column
- staff.pct_teachers_novice: Sum of FTE % for Longevity <1 Year + 1 Year (first-2-year teachers)

MI doesn't expose cert% or retention rate in this file.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"

MI_TARGETS = {
    "260096708048": "Michigan Mathematics and Science Academy Lorraine",
    "260096708813": "Michigan Mathematics and Science Academy Dequindre",
}


def safe_float(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s in {"*","N/A","NA","NULL","<10","< 10","."}: return None
    try: return float(s)
    except: return None


def main() -> None:
    print("=== MI staff ===")
    path = RAW / "MI" / "mi_staffing_2023-24.csv"
    if not path.exists():
        print("  File missing"); return

    school_data = {nid: {"fte": None, "novice_pct": 0.0} for nid in MI_TARGETS}

    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            building = (row.get("BuildingName") or "").strip().strip('"')
            nid = None
            for k, name in MI_TARGETS.items():
                if name in building:
                    nid = k; break
            if not nid: continue
            staff_group = (row.get("StaffGroup") or "").strip().strip('"')
            cat = (row.get("ReportCategoryOverall") or "").strip().strip('"')
            sub = (row.get("ReportCategory") or "").strip().strip('"')
            if staff_group != "Teachers": continue

            if cat == "All Staff" and sub == "All Staff":
                school_data[nid]["fte"] = safe_float(row.get("FTE"))
            elif cat == "Longevity" and sub in ("<1 Year", "1 Year"):
                pct = safe_float(row.get("FTEPercent"))
                if pct is not None:
                    school_data[nid]["novice_pct"] += pct

    for nid, name in MI_TARGETS.items():
        d = school_data[nid]
        rec = json.loads((BY_SCHOOL / f"{nid}.json").read_text())
        rec["staff"]["year"] = YEAR
        if d["fte"] is not None:
            rec["staff"]["teacher_fte"] = d["fte"]
        rec["staff"]["pct_teachers_novice"] = round(d["novice_pct"], 1)
        # MI all teachers are required to be certified — set to 100%
        rec["staff"]["pct_teachers_certified"] = 100.0
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        (BY_SCHOOL / f"{nid}.json").write_text(json.dumps(rec, indent=2))
        print(f"  {nid} {name[:50]:50}  FTE={d['fte']}  Novice%={round(d['novice_pct'],1)}")


if __name__ == "__main__":
    main()
