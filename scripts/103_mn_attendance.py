"""
Script 103: Add MN attendance data from manual lookup on Minnesota Report Card.

MN publishes "Consistent Attendance" (% of students attending >=90% of days),
which is the inverse of chronic absenteeism. We convert.

Source: https://rc.education.mn.gov/  (per-school lookup)
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

BY_SCHOOL = Path('/sessions/fervent-ecstatic-euler/mnt/Concept_dashboard/data/by_school')
YEAR = "2023-24"

# Values manually captured from MN Report Card visualization
MN_ATTENDANCE = {
    "270039905179": {"consistent": 73.0, "school": "Minnesota Math and Science Academy"},
    "270045005159": {"consistent": 76.2, "school": "Horizon Science Academy Twin Cities"},
}


def main():
    print("=== MN Attendance ===")
    for nces_id, data in MN_ATTENDANCE.items():
        rec = json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())
        consistent = data["consistent"]
        chronic = round(100 - consistent, 1)
        rec["attendance"]["year"] = YEAR
        # "Consistent Attendance" is the MN-native metric and the closest proxy
        # for average daily attendance. We set both fields:
        rec["attendance"]["avg_daily_attendance_rate"] = consistent
        rec["attendance"]["chronic_absenteeism_rate"] = chronic
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(rec, indent=2))
        print(f"  {nces_id} {data['school'][:45]:45}  Consistent={consistent}%  Chronic Abs={chronic}%")


if __name__ == "__main__":
    main()
