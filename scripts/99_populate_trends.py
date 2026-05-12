"""
Script 99: Populate year-over-year proficiency trends.

Dashboard expects: trends.{ela,math}_proficiency_by_year[year]  for years
  2021-22, 2022-23, 2023-24

Coverage from this pass:
  - Ohio:    2021-22, 2022-23 from BUILDING_ETHNIC files (replaces the wrong PI-score proxy)
  - Indiana: 2021-22, 2022-23 from ILEARN-{2022,2023}-Grade3-8-Final-School files
  - Iowa:    2022-23 from ia_isasp_2022-23.xlsx (already converted to CSV)
  - MI/MO/MN/IL: 2023-24 only (separate prior-year downloads would be required)

The 2023-24 cell was already populated by the per-state scripts 95/97/98.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"


def safe_float(v) -> Optional[float]:
    if v is None: return None
    s = str(v).strip().replace("%","").replace('"','').replace(",","")
    if not s or s in {"*","***","N/A","NA","NULL","<10",".","PNTS","**","-","NC","PS"}: return None
    if s.startswith("<="):
        try: return round(float(s[2:]) / 2.0, 1)
        except: return None
    if s.startswith(">="):
        try: return round((float(s[2:]) + 100) / 2.0, 1)
        except: return None
    if s.startswith("<"):
        try: return round(float(s[1:]) / 2.0, 1)
        except: return None
    try: return float(s)
    except: return None


def load_school(nces_id: str) -> dict:
    return json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())


def save_school(nces_id: str, record: dict) -> None:
    record["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(record, indent=2))


def set_trend(rec: dict, year: str, ela: Optional[float], math: Optional[float]) -> None:
    rec["trends"].setdefault("ela_proficiency_by_year", {})[year] = ela
    rec["trends"].setdefault("math_proficiency_by_year", {})[year] = math


# ---------------------------------------------------------------------------
# OHIO — parse BUILDING_ETHNIC for each year, compute ELA/Math composite per IRN
# ---------------------------------------------------------------------------

OH_NCES_TO_IRN = {
    "390045105010": "000825", "390051005220": "000338", "390004002939": "133629",
    "390047005029": "000858", "390045405013": "000838", "390136505544": "011533",
    "390138905567": "011986", "390004202978": "133660", "390132205440": "009179",
    "390160605963": "133660", "390135305483": "133660", "390064505319": "008280",
    "390044405003": "000808", "390136605556": "011534", "390138305625": "011976",
    "390044105000": "000804",
}


def compute_oh_proficiency(rows: list[dict]) -> tuple[Optional[float], Optional[float]]:
    """Weighted avg across race rows. Same logic as the 2023-24 OH parser."""
    if not rows:
        return (None, None)
    ela_w, math_w = [], []
    for row in rows:
        group = (row.get("Student Group") or "").strip().strip('"').upper()
        if group in {"", "ALL STUDENTS"}:
            continue
        # Find enrollment column for this year
        enroll = None
        for k, v in row.items():
            if k and k.startswith("Enrollment "):
                enroll = safe_float(v)
                break
        if enroll is None or enroll <= 0:
            continue
        ela_cells = []
        math_cells = []
        for col, val in row.items():
            if not col or "Percent Proficient" not in col:
                continue
            v = safe_float(val)
            if v is None:
                continue
            if "Science" in col:
                continue
            elif "English Language Arts" in col or "English II" in col or re.search(r"\bEnglish\b", col):
                ela_cells.append(v)
            elif "Math" in col or "Algebra" in col or "Geometry" in col:
                math_cells.append(v)
        if ela_cells:
            ela_w.append((sum(ela_cells) / len(ela_cells), enroll))
        if math_cells:
            math_w.append((sum(math_cells) / len(math_cells), enroll))

    def wavg(pairs):
        n = sum(v * w for v, w in pairs)
        d = sum(w for _, w in pairs)
        return round(n / d, 1) if d > 0 else None

    return (wavg(ela_w), wavg(math_w))


def populate_oh_trends() -> None:
    print("\n=== OHIO TRENDS ===")
    files_by_year = {
        "2022-23": RAW / "OH" / "_csv" / "oh_ethnic_2022-23.csv",
        "2021-22": RAW / "OH" / "_csv" / "oh_ethnic_2021-22.csv",
    }
    rows_by_year_irn: dict[str, dict[str, list]] = {}
    for year, path in files_by_year.items():
        if not path.exists():
            print(f"  {year}: file missing")
            continue
        by_irn = {}
        with path.open(encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                irn = (row.get("Building IRN") or "").strip()
                if irn:
                    by_irn.setdefault(irn, []).append(row)
        rows_by_year_irn[year] = by_irn

    for nces_id, irn in OH_NCES_TO_IRN.items():
        if not irn:
            continue
        rec = load_school(nces_id)
        for year, by_irn in rows_by_year_irn.items():
            ela, math = compute_oh_proficiency(by_irn.get(irn, []))
            set_trend(rec, year, ela, math)
        save_school(nces_id, rec)
        ela22 = rec["trends"]["ela_proficiency_by_year"].get("2021-22")
        ela23 = rec["trends"]["ela_proficiency_by_year"].get("2022-23")
        ela24 = rec["trends"]["ela_proficiency_by_year"].get("2023-24")
        print(f"  {nces_id} IRN={irn}  ELA: {ela22} → {ela23} → {ela24}")


# ---------------------------------------------------------------------------
# INDIANA — ILEARN file format identical across years
# ---------------------------------------------------------------------------

IN_TARGETS = {
    "180006702416": ["IN Math & Science Academy"],
    "180009402487": ["IN Math & Science Academy - North"],
}


def parse_in_year(csv_path: Path) -> dict[str, Optional[float]]:
    """Extract School Total proficiency % (last column block 46-52) keyed by school name."""
    if not csv_path.exists():
        return {}
    with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    header_row = next((i for i, r in enumerate(rows) if any("Corp ID" in (c or "") for c in r)), None)
    if header_row is None:
        return {}
    # School Total Proficient % is column 52 (last % column)
    out = {}
    for r in rows[header_row + 1:]:
        if len(r) <= 52:
            continue
        name = (r[3] or "").strip()
        val = safe_float(r[52])
        if not name or val is None:
            continue
        pct = val * 100 if val <= 1.0 else val
        out[name] = round(pct, 1)
    return out


def populate_in_trends() -> None:
    print("\n=== INDIANA TRENDS ===")
    for year, suffix in [("2021-22", "2021-22"), ("2022-23", "2022-23")]:
        ela_path = RAW / "IN" / f"in_ilearn_ela_{suffix}.csv"
        math_path = RAW / "IN" / f"in_ilearn_math_{suffix}.csv"
        ela_data = parse_in_year(ela_path)
        math_data = parse_in_year(math_path)
        for nces_id, patterns in IN_TARGETS.items():
            rec = load_school(nces_id)
            ela = math = None
            for p in patterns:
                if p in ela_data and ela is None:
                    ela = ela_data[p]
                if p in math_data and math is None:
                    math = math_data[p]
            set_trend(rec, year, ela, math)
            save_school(nces_id, rec)
            print(f"  {nces_id} [{year}]  {patterns[0]:38}  ELA={ela}  Math={math}")


# ---------------------------------------------------------------------------
# IOWA — has 2022-23 csv
# ---------------------------------------------------------------------------

def parse_ia_year(csv_path: Path) -> dict[str, dict]:
    """Weighted avg of % proficient across grade cols, by school. Same as 2024-25 parser."""
    if not csv_path.exists():
        return {}
    out: dict[str, dict] = {}
    with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    header_row = next((i for i, r in enumerate(rows) if any("School Name" in (c or "") for c in r)), None)
    if header_row is None:
        return out
    hdr = rows[header_row]
    name_idx = hdr.index("School Name")
    grade_cols = []
    for j, h in enumerate(hdr):
        if h and h.endswith("% Proficient"):
            grade_cols.append((j, j - 1))
    for r in rows[header_row + 1:]:
        if len(r) <= name_idx:
            continue
        name = (r[name_idx] or "").strip()
        if not name:
            continue
        num = 0.0
        den = 0.0
        for pct_idx, tot_idx in grade_cols:
            if pct_idx >= len(r) or tot_idx >= len(r):
                continue
            pct = safe_float(r[pct_idx])
            tot = safe_float(r[tot_idx])
            if pct is None or tot is None or tot <= 0:
                continue
            num += pct * tot
            den += tot
        if den > 0:
            out[name] = {"pct": round(num / den, 1), "n": den}
    return out


def populate_ia_trends() -> None:
    print("\n=== IOWA TRENDS ===")
    ela = parse_ia_year(RAW / "IA" / "ia_isasp_ela_2022-23.csv")
    math = parse_ia_year(RAW / "IA" / "ia_isasp_math_2022-23.csv")
    targets = {
        "199902002316": "Horizon Science Academy Des Moines",
        "199903302345": "Horizon Science Academy Davenport",
    }
    for nces_id, name in targets.items():
        rec = load_school(nces_id)
        e = ela.get(name, {}).get("pct")
        m = math.get(name, {}).get("pct")
        # Iowa's site labels are confusing. The 2022-23 file we have represents the school
        # year ending spring 2023 -> 2022-23 trend slot.
        set_trend(rec, "2022-23", e, m)
        save_school(nces_id, rec)
        print(f"  {nces_id} [2022-23]  {name:40}  ELA={e}  Math={m}")


# ---------------------------------------------------------------------------

def sync_current_year_trends() -> None:
    """For every school, copy the current assessment.{ela,math}.pct_proficient_all
    into the matching trend slot. Fixes OH where script 97 had written PI Score
    (different scale) into the 2023-24 trend cell."""
    print("\n=== SYNC CURRENT-YEAR TRENDS FROM ASSESSMENT FIELD ===")
    fixed = 0
    for path in BY_SCHOOL.glob("*.json"):
        rec = json.loads(path.read_text())
        year = rec.get("assessment", {}).get("year")
        if not year:
            continue
        ela = rec["assessment"]["ela"]["pct_proficient_all"]
        math = rec["assessment"]["math"]["pct_proficient_all"]
        trends = rec.setdefault("trends", {})
        trends.setdefault("ela_proficiency_by_year", {})[year] = ela
        trends.setdefault("math_proficiency_by_year", {})[year] = math
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(rec, indent=2))
        fixed += 1
    print(f"  Synced {fixed} schools")


IL_TARGETS = {
    "170993005092": "Chicago Math & Sci Elem Charter",
    "170141206309": "Horizon Science Acad-Belmont Charter Sch",
    "170141006254": "Horizon Science Acad-McKinley Park Charter Sch",
    "170993006331": "Horizon Sci Academy - Southwest Charter",
}


def populate_il_trends() -> None:
    """IL prior-year files use '% ELA Proficiency' / '% Math Proficiency' columns
    in the 'ELA Math Science' sheet. (The 2023-24 file uses a different per-Total
    column — that one's already populated by 96.)"""
    print("\n=== ILLINOIS TRENDS ===")
    for year in ("2022-23", "2021-22"):
        path = RAW / "IL" / f"il_assessment_ela_math_science_{year}.csv"
        if not path.exists():
            print(f"  {year}: file missing")
            continue
        rows_by_name = {}
        with path.open(encoding="utf-8-sig", errors="replace") as f:
            rdr = csv.reader(f)
            hdr = next(rdr)
            ela_idx = hdr.index("% ELA Proficiency")
            math_idx = hdr.index("% Math Proficiency")
            sn_idx = hdr.index("School Name")
            for r in rdr:
                if len(r) > max(ela_idx, math_idx, sn_idx):
                    rows_by_name[r[sn_idx].strip()] = r
        for nces_id, name in IL_TARGETS.items():
            r = rows_by_name.get(name)
            ela = safe_float(r[ela_idx]) if r else None
            math = safe_float(r[math_idx]) if r else None
            rec = load_school(nces_id)
            set_trend(rec, year, ela, math)
            save_school(nces_id, rec)
            print(f"  {nces_id} [{year}]  {name[:45]:45}  ELA={ela}  Math={math}")


MO_TARGETS = {
    "290059203174": "GATEWAY SCIENCE ACAD/ST LOUIS",
    "290059203205": "GATEWAY SCIENCE ACADEMY HIGH",
    "290059203244": "GATEWAY SCIENCE ACADEMY MIDDLE",
    "290059203241": "GATEWAY SCIENCE ACAD-SOUTH ELE",
}


def populate_mo_trends() -> None:
    """MO MAP school file, Total rows, weighted by ACCOUNTABLE n."""
    print("\n=== MISSOURI TRENDS ===")
    for year, suffix in [("2022-23", "2022-23"), ("2021-22", "2021-22")]:
        path = RAW / "MO" / f"mo_map_school_{suffix}.csv"
        if not path.exists():
            print(f"  {year}: file missing")
            continue
        per_school: dict[str, dict] = {n: {"ela": [], "math": []} for n in MO_TARGETS.values()}
        with path.open(encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                school = (row.get("SCHOOL_NAME") or "").strip()
                if school not in per_school:
                    continue
                if (row.get("CATEGORY") or "").strip() != "Total":
                    continue
                content = (row.get("CONTENT_AREA") or "").lower()
                n = safe_float(row.get("ACCOUNTABLE"))
                pct_prof = safe_float(row.get("PROFICIENT_PCT")) or 0
                pct_adv = safe_float(row.get("ADVANCED_PCT")) or 0
                if n is None or n <= 0:
                    continue
                aoa = pct_prof + pct_adv
                if "language" in content:
                    per_school[school]["ela"].append((aoa, n))
                elif "math" in content:
                    per_school[school]["math"].append((aoa, n))

        def wavg(pairs):
            n = sum(v * w for v, w in pairs); d = sum(w for _, w in pairs)
            return round(n / d, 1) if d > 0 else None

        for nces_id, school_name in MO_TARGETS.items():
            d = per_school[school_name]
            ela = wavg(d["ela"]); math = wavg(d["math"])
            rec = load_school(nces_id)
            set_trend(rec, year, ela, math)
            save_school(nces_id, rec)
            print(f"  {nces_id} [{year}]  {school_name:40}  ELA={ela}  Math={math}")


MN_TARGETS = {
    "270039905179": ["MMSA Elementary School", "MMSA Secondary School"],
    "270045005159": ["Horizon Science Academy Twin Cities"],
}


def _populate_mn_trend_year(year: str, suffix: str) -> None:
    files = {
        "ela": RAW / "MN" / f"mn_mca_reading_{suffix}.csv",
        "math": RAW / "MN" / f"mn_mca_math_{suffix}.csv",
    }
    per_school: dict[str, dict[str, list]] = {}
    for nid, patterns in MN_TARGETS.items():
        per_school[nid] = {"ela": [], "math": []}

    for subject, path in files.items():
        if not path.exists(): continue
        with path.open(encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                school = (row.get("School Name") or "").strip()
                cat = (row.get("Group Category") or "").strip()
                grp = (row.get("Student Group") or "").strip().lower()
                if cat != "All Categories" or grp != "all students":
                    continue
                n = safe_float(row.get("Total Tested"))
                pct = safe_float(row.get("Percent Proficient"))
                if n is None or pct is None or n <= 0: continue
                if pct <= 1.0: pct *= 100
                for nid, patterns in MN_TARGETS.items():
                    if any(school == p or school.startswith(p) for p in patterns):
                        per_school[nid][subject].append((pct, n))
                        break

    def wavg(pairs):
        n = sum(v * w for v, w in pairs); d = sum(w for _, w in pairs)
        return round(n / d, 1) if d > 0 else None

    for nid, patterns in MN_TARGETS.items():
        ela = wavg(per_school[nid]["ela"]); math = wavg(per_school[nid]["math"])
        rec = load_school(nid)
        set_trend(rec, year, ela, math)
        save_school(nid, rec)
        print(f"  {nid} [{year}]  {patterns[0]:42}  ELA={ela}  Math={math}")


def populate_mn_trends() -> None:
    """MN MCA trends. 'All Categories' + 'All students'. Note Iowa-style year labeling:
    file year (e.g. 2023) = test administration year = end of school year (2022-23)."""
    print("\n=== MINNESOTA TRENDS ===")
    _populate_mn_trend_year("2022-23", "2022-23")   # file labeled 2023 = SY 2022-23
    _populate_mn_trend_year("2021-22", "2021-22")   # file labeled 2022 = SY 2021-22


MI_TARGETS_TRENDS = {
    "260096708048": "Michigan Mathematics and Science Academy Lorraine",
    "260096708813": "Michigan Mathematics and Science Academy Dequindre",
}


def populate_mi_trends() -> None:
    """MI MSTEP prior-year files: weighted avg of ELA + Math All Students rows."""
    print("\n=== MICHIGAN TRENDS ===")
    for year in ("2022-23", "2021-22"):
        files = [
            RAW / "MI" / f"mi_mstep_grades_3-8_{year}.csv",
            RAW / "MI" / f"mi_mstep_high_school_{year}.csv",
        ]
        per_school: dict[str, dict] = {nid: {"ela": [], "math": []} for nid in MI_TARGETS_TRENDS}
        for path in files:
            if not path.exists(): continue
            with path.open(encoding="utf-8-sig", errors="replace") as f:
                for row in csv.DictReader(f):
                    building = (row.get("BuildingName") or "").strip().strip('"')
                    nid = None
                    for k, name in MI_TARGETS_TRENDS.items():
                        if name in building:
                            nid = k; break
                    if not nid: continue
                    subject_raw = (row.get("Subject") or "").strip().strip('"').lower()
                    category = (row.get("ReportCategory") or "").strip().strip('"')
                    if category != "All Students": continue
                    n = safe_float(row.get("NumberAssessed"))
                    pct_adv = safe_float(row.get("PercentAdvanced"))
                    pct_prof = safe_float(row.get("PercentProficient"))
                    if n is None or n <= 0: continue
                    aoa = (pct_adv or 0) + (pct_prof or 0) if (pct_adv is not None or pct_prof is not None) else None
                    if aoa is None: continue
                    if "ela" in subject_raw or "english" in subject_raw or "reading" in subject_raw:
                        per_school[nid]["ela"].append((aoa, n))
                    elif "math" in subject_raw:
                        per_school[nid]["math"].append((aoa, n))

        def wavg(pairs):
            n = sum(v * w for v, w in pairs); d = sum(w for _, w in pairs)
            return round(n / d, 1) if d > 0 else None

        for nid, name in MI_TARGETS_TRENDS.items():
            d = per_school[nid]
            ela = wavg(d["ela"]); math = wavg(d["math"])
            rec = load_school(nid)
            set_trend(rec, year, ela, math)
            save_school(nid, rec)
            print(f"  {nid} [{year}]  {name[:50]:50}  ELA={ela}  Math={math}")


def main() -> None:
    populate_oh_trends()
    populate_in_trends()
    populate_ia_trends()
    populate_il_trends()
    populate_mo_trends()
    populate_mn_trends()
    populate_mi_trends()
    sync_current_year_trends()
    print("\nDone. Re-run scripts/10_aggregate.py.")


if __name__ == "__main__":
    main()
