"""
Script 100: More fills from data already on disk.

- Michigan SGP (growth) for MMSA Lorraine + Dequindre — parses mi_performance_sgp_2023-24.csv,
  filters to TestingGroup=All Students and Grade=All Grades, takes MeanSGP per subject.
- Missouri ELL% and SpEd% from mo_map_enrollment_2023-24.csv (was missed in earlier pass).

Skipped: il_assessment_sgp_2023-24.csv contains only statewide aggregates by demographic
group — not per-school growth — so it can't fill the IL growth fields. OH growth is
already populated by 97. MN North Star "Math Ach"/"Reading Ach" percentiles are populated
in accountability.state_percentile_rank already.
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


def safe_float(v) -> Optional[float]:
    if v is None: return None
    s = str(v).strip().replace("%","").replace('"','').replace(",","")
    if not s or s in {"*","***","N/A","NA","NULL","<10","< 10",".","PNTS","**","-","NC","PS"}: return None
    try: return float(s)
    except: return None


def load(nid): return json.loads((BY_SCHOOL/f"{nid}.json").read_text())
def save(nid, rec):
    rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL/f"{nid}.json").write_text(json.dumps(rec, indent=2))


# Michigan SGP
MI_TARGETS = {
    "260096708048": "Michigan Mathematics and Science Academy Lorraine",
    "260096708813": "Michigan Mathematics and Science Academy Dequindre",
}

def populate_mi_growth():
    print("\n=== MICHIGAN SGP (growth) ===")
    path = RAW / "MI" / "mi_performance_sgp_2023-24.csv"
    # Aggregate by school × subject (All Grades + All Students rows)
    sgp_data = {nid: {"ela": [], "math": []} for nid in MI_TARGETS}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            building = (row.get("BuildingName") or "").strip().strip('"')
            nid = None
            for k, name in MI_TARGETS.items():
                if name in building:
                    nid = k; break
            if not nid: continue
            grade = (row.get("Grade") or "").strip().strip('"')
            subject = (row.get("Subject") or "").strip().strip('"').lower()
            testgrp = (row.get("TestingGroup") or "").strip().strip('"')
            if testgrp != "All Students": continue
            if grade != "All Grades": continue
            mean_sgp = safe_float(row.get("MeanSGP"))
            n = safe_float(row.get("TotalIncluded"))
            if mean_sgp is None: continue
            if "english" in subject or "ela" in subject:
                sgp_data[nid]["ela"].append((mean_sgp, n or 1))
            elif "math" in subject:
                sgp_data[nid]["math"].append((mean_sgp, n or 1))

    for nid, name in MI_TARGETS.items():
        d = sgp_data[nid]
        # Should be single row per subject when filtering All Grades + All Students
        ela = d["ela"][0][0] if d["ela"] else None
        math = d["math"][0][0] if d["math"] else None
        rec = load(nid)
        rec["growth"]["year"] = YEAR
        rec["growth"]["source"] = "Michigan MDE"
        rec["growth"]["metric_name"] = "Student Growth Percentile (SGP)"
        if ela is not None: rec["growth"]["ela_growth"] = ela
        if math is not None: rec["growth"]["math_growth"] = math
        # 50 is the median — call out very high or low overall
        if ela is not None and math is not None:
            avg = (ela + math) / 2.0
            rec["growth"]["overall_growth_rating"] = (
                "Well Above Avg" if avg >= 65 else
                "Above Avg" if avg >= 55 else
                "Average" if 45 <= avg < 55 else
                "Below Avg" if avg >= 35 else
                "Well Below Avg"
            )
        save(nid, rec)
        print(f"  {nid} {name[:50]:50}  ELA SGP={ela}  Math SGP={math}")


# Missouri ELL + SpEd
MO_TARGETS = {
    "290059203174": "GATEWAY SCIENCE ACAD/ST LOUIS",
    "290059203205": "GATEWAY SCIENCE ACADEMY HIGH",
    "290059203244": "GATEWAY SCIENCE ACADEMY MIDDLE",
    "290059203241": "GATEWAY SCIENCE ACAD-SOUTH ELE",
}

def populate_mo_extras():
    print("\n=== MISSOURI ELL% + SpEd% ===")
    path = RAW / "MO" / "mo_map_enrollment_2023-24.csv"
    rows_by_name = {}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            if r.get("YEAR") != "2024": continue
            rows_by_name[r.get("SCHOOL_NAME", "").strip()] = r
    for nid, name in MO_TARGETS.items():
        r = rows_by_name.get(name)
        if not r: continue
        rec = load(nid)
        ell = safe_float(r.get("ELL_LEP_STUDENTS_ENROLLED_K_12_PCT"))
        sped = safe_float(r.get("IEP_INCIDENCE_RATE"))
        if ell is not None: rec["enrollment"]["pct_ell"] = ell
        if sped is not None: rec["enrollment"]["pct_sped"] = sped
        save(nid, rec)
        print(f"  {nid} {name[:50]:50}  ELL%={ell}  SpEd%={sped}")


def main():
    populate_mi_growth()
    populate_mo_extras()
    print("\nDone. Re-run scripts/10_aggregate.py.")


if __name__ == "__main__":
    main()
