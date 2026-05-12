"""
Script 201: Fix MN proficiency to use Grade=0 + All students summary row only.

Bug: 08_fetch_mn.py iterated all rows for a school and last-row-wins,
which often was a single-grade or single-subgroup row, not the all-grades-
all-students summary. Slight off-by-fractional-pp errors result.

Fix: filter to Grade='0' and Student Group='All students', then weighted-avg
across matching school rows (MMSA has 2 entries).
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"

MN_TARGETS = {
    "270045005159": ["Horizon Science Academy Twin Cities"],
    "270039905179": ["MMSA Elementary School", "MMSA Secondary School"],
}


def safe_float(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s.upper() in {"*","N/A","NA","NULL","<10",".","-","NC"}: return None
    try: return float(s)
    except: return None


def weighted_pct(file_path, school_names):
    if not file_path.exists(): return None
    matched = []
    with file_path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            sn = (r.get("School Name") or "").strip()
            if sn not in school_names: continue
            if (r.get("Student Group") or "").strip() != "All students": continue
            if (r.get("Grade") or "").strip() != "0": continue
            tested = safe_float(r.get("Count Valid Scores MCA"))
            pct = safe_float(r.get("Percent Proficient"))
            if tested and pct is not None:
                matched.append((tested, pct))
    if not matched: return None
    total = sum(t for t, _ in matched)
    if total == 0: return None
    return round(sum(t * p for t, p in matched) / total * 100, 1)


def main():
    print("=== Fixing MN proficiency to use Grade=0 + All students ===")
    for nid, names in MN_TARGETS.items():
        ela = weighted_pct(RAW / "MN" / "mn_mca_reading_2023-24.csv", names)
        math = weighted_pct(RAW / "MN" / "mn_mca_math_2023-24.csv", names)
        path = BY_SCHOOL / f"{nid}.json"
        if not path.exists(): continue
        rec = json.loads(path.read_text())
        old_ela = ((rec.get("assessment") or {}).get("ela") or {}).get("pct_proficient_all")
        old_math = ((rec.get("assessment") or {}).get("math") or {}).get("pct_proficient_all")
        if ela is not None:
            rec.setdefault("assessment", {}).setdefault("ela", {})["pct_proficient_all"] = ela
        if math is not None:
            rec.setdefault("assessment", {}).setdefault("math", {})["pct_proficient_all"] = math
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(rec, indent=2))
        print(f"  {nid} {rec['meta']['school_name'][:40]:40}  ELA: {old_ela} → {ela}  Math: {old_math} → {math}")


if __name__ == "__main__":
    main()
