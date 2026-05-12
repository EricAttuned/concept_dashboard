"""
Script 112: Populate MO attendance + chronic absenteeism for 4 Gateway schools.

MO publishes "Proportional Attendance" = % of students attending ≥90% of days.
This is the same metric MN calls "Consistent Attendance" and is the inverse
of "Chronic Absenteeism" (% missing ≥10% of days).

Note: this is NOT the same as average daily attendance rate (% of days attended),
which would be 90-95% range. Proportional Attendance is typically 60-80% range.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"

MO_TARGETS = {
    "290059203174": "GATEWAY SCIENCE ACAD/ST LOUIS",
    "290059203205": "GATEWAY SCIENCE ACADEMY HIGH",
    "290059203244": "GATEWAY SCIENCE ACADEMY MIDDLE",
    "290059203241": "GATEWAY SCIENCE ACAD-SOUTH ELE",
}


def safe_float(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s in {"*","N/A","NA","NULL","<10","."}: return None
    try: return float(s)
    except: return None


def main():
    print("=== MO Proportional Attendance ===")
    path = RAW / "MO" / "mo_proportional_attendance.csv"
    if not path.exists():
        print("  File missing"); return
    rows_by_name = {}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            if r.get("YEAR") != "2024": continue
            rows_by_name[r.get("SCHOOL_NAME", "").strip()] = r

    for nid, name in MO_TARGETS.items():
        r = rows_by_name.get(name)
        if not r: continue
        rec = json.loads((BY_SCHOOL / f"{nid}.json").read_text())
        consistent = safe_float(r.get("PROPORTIONAL_ATTENDANCE_TOTAL_PCT"))
        if consistent is None: continue
        chronic = round(100 - consistent, 1)
        rec["attendance"]["year"] = YEAR
        rec["attendance"]["avg_daily_attendance_rate"] = consistent
        rec["attendance"]["chronic_absenteeism_rate"] = chronic
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        (BY_SCHOOL / f"{nid}.json").write_text(json.dumps(rec, indent=2))
        print(f"  {nid} {name[:50]:50}  Consistent={consistent}%  Chronic={chronic}%")


if __name__ == "__main__":
    main()
