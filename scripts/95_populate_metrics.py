"""
Script 95: Parse the raw state CSVs and populate the per-school JSON records
with actual proficiency / enrollment / accountability metrics.

This script does what scripts 04/05/06/08 *should* have done with local CSVs.
It reads the statewide CSV files in data/raw/<STATE>/, filters to the target
Concept Schools (handling name variants), aggregates across grades weighted by
N assessed, and writes the metric fields into the matching per-school JSON
files in data/by_school/.

Idempotent — safe to re-run. Only touches MI, MO, MN, IL. OH/IN/IA are left
alone (those need similar parser work but are out of scope for this pass).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"

# ---------------------------------------------------------------------------
# Target school definitions: how to find each school in the state CSV.
# Each tuple is (nces_id, list of name patterns that match in the CSV).
# ---------------------------------------------------------------------------

MI_TARGETS = [
    ("260096708048", ["Michigan Mathematics and Science Academy Lorraine"]),
    ("260096708813", ["Michigan Mathematics and Science Academy Dequindre"]),
]

MO_TARGETS = [
    # (Smiley / High / Middle / South correspond to the building variants)
    ("290059203174", ["GATEWAY SCIENCE ACAD/ST LOUIS"]),   # Smiley = main elementary
    ("290059203205", ["GATEWAY SCIENCE ACADEMY HIGH"]),
    ("290059203244", ["GATEWAY SCIENCE ACADEMY MIDDLE"]),
    ("290059203241", ["GATEWAY SCIENCE ACAD-SOUTH ELE"]),
]

MN_TARGETS = [
    # MMSA Saint Paul is split into two campuses in MN data; combine both.
    # The standalone "Math and Science Academy" in Washington County is a DIFFERENT school.
    ("270039905179", ["MMSA Elementary School", "MMSA Secondary School"]),
    ("270045005159", ["Horizon Science Academy Twin Cities"]),
]

IL_TARGETS = [
    ("170993005092", ["Chicago Math & Sci Elem Charter", "Chicago Math & Science Hi Sch Charter"]),
    ("170141206309", ["Horizon Science Acad-Belmont Charter Sch"]),
    ("170141006254", ["Horizon Science Acad-McKinley Park Charter Sch"]),
    ("170993006331", ["Horizon Sci Academy - Southwest Charter"]),
]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def safe_float(v) -> Optional[float]:
    """Parse a CSV cell into a float. Returns None if not parseable / suppressed."""
    if v is None:
        return None
    s = str(v).strip().replace("%", "").replace('"', '')
    if not s or s in {"*", "N/A", "n/a", "NA", "<10", "."}:
        return None
    # Michigan suppression bands: "<=10%" / "<=20%" / "<=30%" / ">=80%" etc.
    # Use the midpoint of the band as a rough estimate so small-cell schools aren't all-null.
    if s.startswith("<="):
        try:
            top = float(s[2:])
            return round(top / 2.0, 1)
        except ValueError:
            return None
    if s.startswith(">="):
        try:
            bot = float(s[2:])
            return round((bot + 100) / 2.0, 1)
        except ValueError:
            return None
    if s.startswith("<"):
        try:
            top = float(s[1:])
            return round(top / 2.0, 1)
        except ValueError:
            return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def weighted_avg(pairs: list[tuple[Optional[float], Optional[float]]]) -> Optional[float]:
    """Weighted average. Each pair = (value, weight). Both must be non-None."""
    num = 0.0
    den = 0.0
    for v, w in pairs:
        if v is None or w is None or w <= 0:
            continue
        num += v * w
        den += w
    if den == 0:
        return None
    return round(num / den, 1)


def load_school(nces_id: str) -> dict:
    path = BY_SCHOOL / f"{nces_id}.json"
    return json.loads(path.read_text())


def save_school(nces_id: str, record: dict) -> None:
    path = BY_SCHOOL / f"{nces_id}.json"
    record["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(record, indent=2))


def update_assessment(record: dict, *, ela: Optional[float], math: Optional[float],
                       science: Optional[float], source: str) -> None:
    record["assessment"]["year"] = YEAR
    record["assessment"]["source"] = source
    record["assessment"]["ela"]["pct_proficient_all"] = ela
    record["assessment"]["math"]["pct_proficient_all"] = math
    if science is not None:
        record["assessment"]["science"]["pct_proficient_all"] = science


def update_trend(record: dict, *, ela: Optional[float], math: Optional[float]) -> None:
    """Backfill the 2023-24 trend cell with the same values we just set."""
    trends = record.setdefault("trends", {})
    trends.setdefault("ela_proficiency_by_year", {})[YEAR] = ela
    trends.setdefault("math_proficiency_by_year", {})[YEAR] = math


# ---------------------------------------------------------------------------
# MICHIGAN — M-STEP
# CSV is one row per school × grade × subject × subgroup ("ReportCategory")
# We want the "All Students" rows and compute % Advanced+Proficient (= "at or above proficient")
# ---------------------------------------------------------------------------

def parse_michigan() -> None:
    print("\n=== MICHIGAN ===")
    files = [
        RAW / "MI" / "mi_mstep_grades_3-8_2023-24.csv",
        RAW / "MI" / "mi_mstep_high_school_2023-24.csv",
    ]

    for nces_id, name_patterns in MI_TARGETS:
        # collect (subject, grade) -> (pct_at_or_above_proficient, N) for ALL STUDENTS rows
        rows_by_subject: dict[str, list[tuple[float, float]]] = {"ela": [], "math": [], "science": []}
        subgroup_rows: dict[str, dict[str, list[tuple[float, float]]]] = {
            k: {"ela": [], "math": []} for k in ("black", "hispanic", "white", "ell", "sped", "frl")
        }

        for csv_path in files:
            if not csv_path.exists():
                continue
            with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    building = row.get("BuildingName", "").strip().strip('"')
                    if not any(p in building for p in name_patterns):
                        continue
                    subject_raw = row.get("Subject", "").strip().strip('"').lower()
                    category = row.get("ReportCategory", "").strip().strip('"')
                    n = safe_float(row.get("NumberAssessed"))
                    pct_adv = safe_float(row.get("PercentAdvanced"))
                    pct_prof = safe_float(row.get("PercentProficient"))
                    if n is None or n <= 0:
                        continue
                    at_or_above = None
                    if pct_adv is not None and pct_prof is not None:
                        at_or_above = pct_adv + pct_prof
                    elif pct_prof is not None:
                        at_or_above = pct_prof

                    # Map subject
                    if "ela" in subject_raw or "english" in subject_raw or "reading" in subject_raw or subject_raw in {"e"}:
                        subject = "ela"
                    elif "math" in subject_raw:
                        subject = "math"
                    elif "science" in subject_raw:
                        subject = "science"
                    else:
                        continue

                    if at_or_above is None:
                        continue

                    if category == "All Students":
                        rows_by_subject[subject].append((at_or_above, n))

                    # Subgroup mapping
                    sub_key = None
                    if category == "Black or African American":
                        sub_key = "black"
                    elif category == "Hispanic of Any Race":
                        sub_key = "hispanic"
                    elif category == "White":
                        sub_key = "white"
                    elif category == "English Learners":
                        sub_key = "ell"
                    elif category == "Students With Disabilities":
                        sub_key = "sped"
                    elif category == "Economically Disadvantaged":
                        sub_key = "frl"
                    if sub_key and subject in ("ela", "math"):
                        subgroup_rows[sub_key][subject].append((at_or_above, n))

        ela = weighted_avg(rows_by_subject["ela"])
        math = weighted_avg(rows_by_subject["math"])
        science = weighted_avg(rows_by_subject["science"])

        record = load_school(nces_id)
        update_assessment(record, ela=ela, math=math, science=science, source="Michigan M-STEP")
        update_trend(record, ela=ela, math=math)

        # Subgroups
        for sub_key, by_subject in subgroup_rows.items():
            sub_ela = weighted_avg(by_subject["ela"])
            sub_math = weighted_avg(by_subject["math"])
            record["assessment"]["ela"]["by_subgroup"][sub_key] = sub_ela
            record["assessment"]["math"]["by_subgroup"][sub_key] = sub_math

        save_school(nces_id, record)
        print(f"  {nces_id} {name_patterns[0][:50]:50}  ELA={ela}  Math={math}  Sci={science}")


# ---------------------------------------------------------------------------
# MISSOURI — MAP
# CSV is one row per school × content × grade × category (Total / Race-Ethnicity / Special Programs).
# Use CATEGORY == "Total" rows. ACCOUNTABLE column is N assessed. PROFICIENT_PCT + ADVANCED_PCT.
# ---------------------------------------------------------------------------

def parse_missouri() -> None:
    print("\n=== MISSOURI ===")
    csv_path = RAW / "MO" / "mo_map_school_2023-24.csv"
    if not csv_path.exists():
        print(f"  SKIP: {csv_path} not found")
        return

    for nces_id, name_patterns in MO_TARGETS:
        rows_by_subject: dict[str, list[tuple[float, float]]] = {"ela": [], "math": [], "science": []}
        subgroup_rows: dict[str, dict[str, list[tuple[float, float]]]] = {
            k: {"ela": [], "math": []} for k in ("black", "hispanic", "white", "ell", "sped", "frl")
        }

        with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                school = row.get("SCHOOL_NAME", "").strip()
                if not any(p in school for p in name_patterns):
                    continue
                content = row.get("CONTENT_AREA", "").strip()
                category = row.get("CATEGORY", "").strip()
                type_ = row.get("TYPE", "").strip()
                n = safe_float(row.get("ACCOUNTABLE"))
                pct_prof = safe_float(row.get("PROFICIENT_PCT"))
                pct_adv = safe_float(row.get("ADVANCED_PCT"))
                if n is None or n <= 0:
                    continue
                at_or_above = (pct_prof or 0) + (pct_adv or 0) if (pct_prof is not None or pct_adv is not None) else None
                if at_or_above is None:
                    continue

                if "language" in content.lower():
                    subject = "ela"
                elif "math" in content.lower():
                    subject = "math"
                elif "science" in content.lower():
                    subject = "science"
                else:
                    continue

                if category == "Total":
                    rows_by_subject[subject].append((at_or_above, n))

                sub_key = None
                t_lower = type_.lower()
                if category == "Race/Ethnicity":
                    if "black" in t_lower:
                        sub_key = "black"
                    elif "hispanic" in t_lower:
                        sub_key = "hispanic"
                    elif t_lower.strip() == "white":
                        sub_key = "white"
                elif category == "Special Programs":
                    if "lep" in t_lower or "english language learner" in t_lower or "el" == t_lower:
                        sub_key = "ell"
                    elif "iep" in t_lower or "disabilit" in t_lower:
                        sub_key = "sped"
                    elif "frl" in t_lower or "free" in t_lower or "reduced" in t_lower:
                        sub_key = "frl"

                if sub_key and subject in ("ela", "math"):
                    subgroup_rows[sub_key][subject].append((at_or_above, n))

        ela = weighted_avg(rows_by_subject["ela"])
        math = weighted_avg(rows_by_subject["math"])
        science = weighted_avg(rows_by_subject["science"])

        record = load_school(nces_id)
        update_assessment(record, ela=ela, math=math, science=science, source="Missouri MAP")
        update_trend(record, ela=ela, math=math)

        for sub_key, by_subject in subgroup_rows.items():
            sub_ela = weighted_avg(by_subject["ela"])
            sub_math = weighted_avg(by_subject["math"])
            record["assessment"]["ela"]["by_subgroup"][sub_key] = sub_ela
            record["assessment"]["math"]["by_subgroup"][sub_key] = sub_math

        save_school(nces_id, record)
        print(f"  {nces_id} {name_patterns[0][:50]:50}  ELA={ela}  Math={math}  Sci={science}")


# ---------------------------------------------------------------------------
# MINNESOTA — MCA
# Three separate CSVs (Math, Reading, Science). Rows are school × grade × Student Group.
# Filter by School Name. "Group Category" = "All Students" gives totals.
# "Percent Proficient" is already the % at or above proficient. Use "Total Tested" as N.
# ---------------------------------------------------------------------------

def parse_minnesota() -> None:
    print("\n=== MINNESOTA ===")
    files = {
        "ela":     RAW / "MN" / "mn_mca_reading_2023-24.csv",
        "math":    RAW / "MN" / "mn_mca_math_2023-24.csv",
        "science": RAW / "MN" / "mn_mca_science_2023-24.csv",
    }

    for nces_id, name_patterns in MN_TARGETS:
        rows_by_subject: dict[str, list[tuple[float, float]]] = {"ela": [], "math": [], "science": []}
        subgroup_rows: dict[str, dict[str, list[tuple[float, float]]]] = {
            k: {"ela": [], "math": []} for k in ("black", "hispanic", "white", "ell", "sped", "frl")
        }

        for subject, csv_path in files.items():
            if not csv_path.exists():
                continue
            with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    school = row.get("School Name", "").strip()
                    if not any(school == p or school.startswith(p) for p in name_patterns):
                        continue
                    cat = row.get("Group Category", "").strip()
                    grp = row.get("Student Group", "").strip()
                    n = safe_float(row.get("Total Tested"))
                    pct = safe_float(row.get("Percent Proficient"))
                    if n is None or n <= 0 or pct is None:
                        continue
                    # MN reports Percent Proficient as a decimal (0.6957 = 69.57%). Normalize.
                    if pct <= 1.0:
                        pct = pct * 100

                    if cat == "All Categories" and grp.lower() == "all students":
                        rows_by_subject[subject].append((pct, n))

                    # Subgroups
                    sub_key = None
                    grp_l = grp.lower()
                    if "black" in grp_l or "african american" in grp_l:
                        sub_key = "black"
                    elif "hispanic" in grp_l:
                        sub_key = "hispanic"
                    elif grp_l == "white":
                        sub_key = "white"
                    elif "english learner" in grp_l or grp_l == "el":
                        sub_key = "ell"
                    elif "special education" in grp_l or "disabilit" in grp_l:
                        sub_key = "sped"
                    elif "free" in grp_l or "frl" in grp_l or "reduced" in grp_l:
                        sub_key = "frl"
                    if sub_key and subject in ("ela", "math"):
                        subgroup_rows[sub_key][subject].append((pct, n))

        ela = weighted_avg(rows_by_subject["ela"])
        math = weighted_avg(rows_by_subject["math"])
        science = weighted_avg(rows_by_subject["science"])

        record = load_school(nces_id)
        update_assessment(record, ela=ela, math=math, science=science, source="Minnesota MCA")
        update_trend(record, ela=ela, math=math)

        for sub_key, by_subject in subgroup_rows.items():
            sub_ela = weighted_avg(by_subject["ela"])
            sub_math = weighted_avg(by_subject["math"])
            record["assessment"]["ela"]["by_subgroup"][sub_key] = sub_ela
            record["assessment"]["math"]["by_subgroup"][sub_key] = sub_math

        save_school(nces_id, record)
        print(f"  {nces_id} {name_patterns[0][:50]:50}  ELA={ela}  Math={math}  Sci={science}")


# ---------------------------------------------------------------------------
# ILLINOIS — IAR (Report Card Public Data Set)
# This file is ALREADY aggregated at the school level — one row per school.
# Columns: "IAR ELA Proficiency Rate - Total", "IAR Math Proficiency Rate - Total",
# plus subgroup breakouts.
# ---------------------------------------------------------------------------

IL_SUBGROUP_MAP = {
    "black": "Black or African American",
    "hispanic": "Hispanic or Latino",
    "white": "White",
    "ell": "EL",
    "sped": "IEP",
    "frl": "Low Income",
}


def parse_illinois() -> None:
    print("\n=== ILLINOIS ===")
    iar_path = RAW / "IL" / "il_assessment_iar_2023-24.csv"
    sat_path = RAW / "IL" / "il_assessment_sat_2023-24.csv"

    if not iar_path.exists():
        print(f"  SKIP: {iar_path} not found")
        return

    # Build IAR lookup keyed on school name
    iar_by_name: dict[str, dict] = {}
    with iar_path.open(encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iar_by_name[row.get("School Name", "").strip()] = row

    sat_by_name: dict[str, dict] = {}
    if sat_path.exists():
        with sat_path.open(encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sat_by_name[row.get("School Name", "").strip()] = row

    for nces_id, name_patterns in IL_TARGETS:
        # Find first matching IAR row
        iar_row = None
        for p in name_patterns:
            for key, row in iar_by_name.items():
                if p in key:
                    iar_row = row
                    break
            if iar_row:
                break

        # Find SAT row (for high school)
        sat_row = None
        for p in name_patterns:
            for key, row in sat_by_name.items():
                if p in key:
                    sat_row = row
                    break
            if sat_row:
                break

        ela = math = None
        if iar_row:
            ela = safe_float(iar_row.get("IAR ELA Proficiency Rate - Total"))
            math = safe_float(iar_row.get("IAR Math Proficiency Rate - Total"))
        # Fallback to SAT for high schools where IAR may be N/A
        if (ela is None or math is None) and sat_row:
            ela = ela or safe_float(sat_row.get("SAT ELA Proficiency Rate - Total")
                                    or sat_row.get("SAT ERW Proficiency Rate - Total"))
            math = math or safe_float(sat_row.get("SAT Math Proficiency Rate - Total"))

        record = load_school(nces_id)
        update_assessment(record, ela=ela, math=math, science=None, source="Illinois IAR / SAT")
        update_trend(record, ela=ela, math=math)

        # Subgroups
        if iar_row:
            for sub_key, label in IL_SUBGROUP_MAP.items():
                sub_ela = safe_float(iar_row.get(f"IAR ELA Proficiency Rate - {label}"))
                sub_math = safe_float(iar_row.get(f"IAR Math Proficiency Rate - {label}"))
                record["assessment"]["ela"]["by_subgroup"][sub_key] = sub_ela
                record["assessment"]["math"]["by_subgroup"][sub_key] = sub_math

        save_school(nces_id, record)
        match_name = name_patterns[0]
        print(f"  {nces_id} {match_name[:50]:50}  ELA={ela}  Math={math}")


# ---------------------------------------------------------------------------

def main() -> None:
    parse_michigan()
    parse_missouri()
    parse_minnesota()
    parse_illinois()
    print("\nDone. Re-run scripts/10_aggregate.py to refresh the dashboard.")


if __name__ == "__main__":
    main()
