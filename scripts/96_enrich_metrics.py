"""
Script 96: Second-pass enrichment.

Adds demographics, accountability, attendance, growth and graduation metrics
to the MI / MO / MN / IL per-school records — the fields the dashboard cards
expect that script 95 did not populate.

Idempotent. Touches only the per-school JSONs for the 12 target schools.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"


def safe_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace("%", "").replace('"', "").replace("$", "")
    if not s or s in {"*", "N/A", "n/a", "NA", "NULL", "null", "<10", ".", "PNTS", "**", "-"}:
        return None
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


def safe_int(v) -> Optional[int]:
    f = safe_float(v)
    return int(f) if f is not None else None


def load_school(nces_id: str) -> dict:
    return json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())


def save_school(nces_id: str, record: dict) -> None:
    record["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(record, indent=2))


# ---------------------------------------------------------------------------
# ILLINOIS — single row per school in general sheet, has everything
# ---------------------------------------------------------------------------

IL_TARGETS = {
    "170993005092": ["Chicago Math & Sci Elem Charter"],
    "170141206309": ["Horizon Science Acad-Belmont Charter Sch"],
    "170141006254": ["Horizon Science Acad-McKinley Park Charter Sch"],
    "170993006331": ["Horizon Sci Academy - Southwest Charter"],
}


def enrich_illinois() -> None:
    print("\n=== ILLINOIS enrichment ===")
    general_path = RAW / "IL" / "il_assessment_general_2023-24.csv"
    discipline_path = RAW / "IL" / "il_assessment_discipline_2023-24.csv"

    gen_by_name: dict[str, dict] = {}
    with general_path.open(encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            gen_by_name[row.get("School Name", "").strip()] = row

    disc_by_name: dict[str, dict] = {}
    if discipline_path.exists():
        with discipline_path.open(encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                disc_by_name[row.get("School Name", "").strip()] = row

    for nces_id, name_patterns in IL_TARGETS.items():
        gen = None
        disc = None
        for p in name_patterns:
            for key, row in gen_by_name.items():
                if p in key:
                    gen = row
                    break
            if gen:
                break
        for p in name_patterns:
            for key, row in disc_by_name.items():
                if p in key:
                    disc = row
                    break
            if disc:
                break

        if not gen:
            print(f"  {nces_id}: NO general row found")
            continue

        rec = load_school(nces_id)

        # Enrollment
        rec["enrollment"]["year"] = YEAR
        total = safe_int(gen.get("# Student Enrollment"))
        if total is not None:
            rec["enrollment"]["total"] = total
        rec["enrollment"]["by_race_ethnicity"] = {
            "white": safe_int(gen.get("# Student Enrollment - White")),
            "black": safe_int(gen.get("# Student Enrollment - Black or African American")),
            "hispanic": safe_int(gen.get("# Student Enrollment - Hispanic or Latino")),
            "asian": safe_int(gen.get("# Student Enrollment - Asian")),
            "american_indian": safe_int(gen.get("# Student Enrollment - American Indian or Alaska Native")),
            "pacific_islander": safe_int(gen.get("# Student Enrollment - Native Hawaiian or Other Pacific Islander")),
            "two_or_more": safe_int(gen.get("# Student Enrollment - Two or More Races")),
        }
        rec["enrollment"]["pct_free_reduced_lunch"] = safe_float(gen.get("% Student Enrollment - Low Income"))
        rec["enrollment"]["pct_ell"] = safe_float(gen.get("% Student Enrollment - EL"))
        rec["enrollment"]["pct_sped"] = safe_float(gen.get("% Student Enrollment - IEP"))

        # Accountability — Illinois Summative Designation
        designation = (gen.get("Summative Designation") or "").strip()
        if designation and designation.upper() not in {"N/A", "NA", ""}:
            rec["accountability"]["year"] = YEAR
            rec["accountability"]["state_rating"] = designation

        # Attendance + chronic absenteeism (both live in the general sheet)
        attend = safe_float(gen.get("Student Attendance Rate"))
        if attend is not None:
            rec["attendance"]["year"] = YEAR
            rec["attendance"]["avg_daily_attendance_rate"] = attend
        chronic = safe_float(gen.get("Chronic Absenteeism"))
        if chronic is not None:
            rec["attendance"]["year"] = YEAR
            rec["attendance"]["chronic_absenteeism_rate"] = chronic

        # Graduation rate (for high schools)
        grad_4yr = safe_float(gen.get("High School 4-Year Graduation Rate - Total"))
        grad_5yr = safe_float(gen.get("High School 5-Year Graduation Rate - Total"))
        if grad_4yr is not None:
            rec["graduation"]["year"] = YEAR
            rec["graduation"]["four_year_grad_rate"] = grad_4yr
        if grad_5yr is not None:
            rec["graduation"]["five_year_grad_rate"] = grad_5yr

        save_school(nces_id, rec)
        print(f"  {nces_id} {name_patterns[0][:50]:50}  enr={total}  designation={designation[:30] if designation else '-'}  chronic={chronic}")


# ---------------------------------------------------------------------------
# MISSOURI — 2024 row in enrollment file has counts + percents
# ---------------------------------------------------------------------------

MO_TARGETS = {
    "290059203174": "GATEWAY SCIENCE ACAD/ST LOUIS",       # Smiley
    "290059203205": "GATEWAY SCIENCE ACADEMY HIGH",
    "290059203244": "GATEWAY SCIENCE ACADEMY MIDDLE",
    "290059203241": "GATEWAY SCIENCE ACAD-SOUTH ELE",
}


def enrich_missouri() -> None:
    print("\n=== MISSOURI enrichment ===")
    enroll_path = RAW / "MO" / "mo_map_enrollment_2023-24.csv"
    rows_by_name: dict[str, dict] = {}
    with enroll_path.open(encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            if row.get("YEAR", "") != "2024":
                continue
            rows_by_name[row.get("SCHOOL_NAME", "").strip()] = row

    for nces_id, name in MO_TARGETS.items():
        row = rows_by_name.get(name)
        if not row:
            print(f"  {nces_id}: NO 2024 row for {name}")
            continue

        rec = load_school(nces_id)
        rec["enrollment"]["year"] = YEAR
        total = safe_int(row.get("ENROLLMENT_GRADES_K_12"))
        if total is not None:
            rec["enrollment"]["total"] = total
        rec["enrollment"]["by_race_ethnicity"] = {
            "white": safe_int(row.get("ENROLLMENT_WHITE")),
            "black": safe_int(row.get("ENROLLMENT_BLACK")),
            "hispanic": safe_int(row.get("ENROLLMENT_HISPANIC")),
            "asian": safe_int(row.get("ENROLLMENT_ASIAN")),
            "american_indian": safe_int(row.get("ENROLLMENT_INDIAN")),
            "pacific_islander": safe_int(row.get("ENROLLMENT_PACIFIC_ISLANDER")),
            "two_or_more": safe_int(row.get("ENROLLMENT_MULTIRACIAL")),
        }
        rec["enrollment"]["pct_free_reduced_lunch"] = safe_float(row.get("LUNCH_COUNT_FREE_REDUCED_PCT"))

        save_school(nces_id, rec)
        print(f"  {nces_id} {name[:50]:50}  enr={total}  FRL%={rec['enrollment']['pct_free_reduced_lunch']}")


# ---------------------------------------------------------------------------
# MICHIGAN — heavily cross-tabulated enrollment file. We'll only pull totals
# by race (no demographic filter applied per row) and the FRL/ELL/SpEd ratios.
# ---------------------------------------------------------------------------

MI_TARGETS = {
    "260096708048": "Michigan Mathematics and Science Academy Lorraine",
    "260096708813": "Michigan Mathematics and Science Academy Dequindre",
}

MI_RACE_MAP = {
    "Black, not of Hispanic origin": "black",
    "Hispanic of any race": "hispanic",
    "White, not of Hispanic origin": "white",
    "Asian": "asian",
    "American Indian or Alaska Native": "american_indian",
    "Native Hawaiian or Other Pacific Islander": "pacific_islander",
    "Two or More Races": "two_or_more",
}


def enrich_michigan_graduation() -> None:
    """MI graduation rates — 4-year cohort, All Students/All Crosstabs row."""
    print("\n=== MICHIGAN graduation ===")
    path = RAW / "MI" / "mi_performance_graduation_2023-24.csv"
    if not path.exists():
        print(f"  SKIP: {path}")
        return
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            building = (row.get("BuildingName") or "").strip().strip('"')
            for nid, name in MI_TARGETS.items():
                if name in building:
                    subgroup = (row.get("Subgroup") or "").strip().strip('"')
                    crosstabs = (row.get("Crosstabs") or "").strip().strip('"')
                    rate_year = (row.get("RateYear") or "").strip().strip('"')
                    if subgroup == "All Students" and crosstabs == "All Students":
                        grad = safe_float(row.get("GraduationRate"))
                        if grad is not None:
                            rec = load_school(nid)
                            rec["graduation"]["year"] = YEAR
                            if rate_year == "4-Year":
                                rec["graduation"]["four_year_grad_rate"] = grad
                            elif rate_year == "5-Year":
                                rec["graduation"]["five_year_grad_rate"] = grad
                            save_school(nid, rec)
                            print(f"  {nid} {name[:50]:50}  {rate_year}={grad}%")


def enrich_michigan() -> None:
    print("\n=== MICHIGAN enrichment ===")
    path = RAW / "MI" / "mi_performance_enrollment_2023-24.csv"

    # Accumulate per school
    school_data: dict[str, dict] = {nid: {"total": 0, "race": {k: 0 for k in MI_RACE_MAP.values()},
                                            "ell": 0, "frl": 0, "sped": 0,
                                            "ell_total": 0, "frl_total": 0, "sped_total": 0}
                                      for nid in MI_TARGETS}

    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            building = row.get("BUILDING_NAME", "").strip().strip('"')
            nid = None
            for k, name in MI_TARGETS.items():
                if name in building:
                    nid = k
                    break
            if not nid:
                continue
            grade = (row.get("GRADE") or "").strip().strip('"')
            gender = (row.get("GENDER") or "").strip().strip('"')
            race = (row.get("RACE_ETHNICITY") or "").strip().strip('"')
            sped = (row.get("SPECIAL_EDUCATION") or "").strip().strip('"')
            econ = (row.get("ECONOMICALLY_DISADVANTAGED") or "").strip().strip('"')
            ell = (row.get("ENGLISH_LANGUAGE_LEARNERS") or "").strip().strip('"')
            total = safe_int(row.get("TOTAL_ENROLLMENT"))
            if total is None:
                continue

            # School-wide totals: gender blank + race blank + sped blank + econ blank + ell blank
            # gives the "Grade X all-students" cuts. Summing those grade rows = total.
            if not gender and not race and not sped and not econ and not ell:
                # Only sum non-aggregated grade rows (skip if grade is some "All Grades")
                if grade and grade not in {"All Grades", "Total"}:
                    school_data[nid]["total"] += total

            # Race counts: ONLY race set, all others blank, gender blank
            if race and not gender and not sped and not econ and not ell:
                key = MI_RACE_MAP.get(race)
                if key:
                    school_data[nid]["race"][key] += total

            # ELL: ELL field set with specific value
            if ell == "English Learners" and not race and not gender and not sped and not econ:
                school_data[nid]["ell"] += total
            if ell in {"English Learners", "Not English Learners"} and not race and not gender and not sped and not econ:
                school_data[nid]["ell_total"] += total

            # FRL (Economically Disadvantaged)
            if econ == "Economically Disadvantaged" and not race and not gender and not sped and not ell:
                school_data[nid]["frl"] += total
            if econ in {"Economically Disadvantaged", "Not Economically Disadvantaged"} and not race and not gender and not sped and not ell:
                school_data[nid]["frl_total"] += total

            # SpEd
            if sped == "Students with Disabilities" and not race and not gender and not econ and not ell:
                school_data[nid]["sped"] += total
            if sped in {"Students with Disabilities", "Students without IEP"} and not race and not gender and not econ and not ell:
                school_data[nid]["sped_total"] += total

    for nid, name in MI_TARGETS.items():
        d = school_data[nid]
        rec = load_school(nid)
        rec["enrollment"]["year"] = YEAR
        if d["total"] > 0:
            rec["enrollment"]["total"] = d["total"]
        rec["enrollment"]["by_race_ethnicity"] = d["race"]
        rec["enrollment"]["pct_ell"] = round(100 * d["ell"] / d["ell_total"], 1) if d["ell_total"] > 0 else None
        rec["enrollment"]["pct_free_reduced_lunch"] = round(100 * d["frl"] / d["frl_total"], 1) if d["frl_total"] > 0 else None
        rec["enrollment"]["pct_sped"] = round(100 * d["sped"] / d["sped_total"], 1) if d["sped_total"] > 0 else None
        save_school(nid, rec)
        print(f"  {nid} {name[:50]:50}  total={d['total']}  FRL%={rec['enrollment']['pct_free_reduced_lunch']}  ELL%={rec['enrollment']['pct_ell']}")


# ---------------------------------------------------------------------------
# MINNESOTA — pull accountability rating from North Star / MMR file.
# The MMR file has weird preamble — real header is row 5.
# ---------------------------------------------------------------------------

MN_TARGETS = {
    # MMSA Saint Paul = MMSA Elementary + MMSA Secondary in Ramsey County
    "270039905179": ["MMSA Elementary School", "MMSA Secondary School"],
    "270045005159": ["Horizon Science Academy Twin Cities"],
}


def enrich_minnesota() -> None:
    """
    Parse the MN North Star / MMR accountability file. This file only contains
    schools 'identified for support' under ESSA. Schools NOT in the file are
    in good standing (= "Not Identified"). We mark schools accordingly.
    """
    print("\n=== MINNESOTA enrichment ===")
    path = RAW / "MN" / "mn_mca_mmr_accountability_2023-24.csv"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return

    import io as _io
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()
    header_idx = next((i for i, ln in enumerate(lines) if ln.startswith("Year,District Number")), None)
    if header_idx is None:
        print("  Could not find header row")
        return

    body = "".join(lines[header_idx:])
    rows = []
    for row in csv.DictReader(_io.StringIO(body)):
        clean = {(k.replace("\n", " ").strip() if k else k): v for k, v in row.items()}
        rows.append(clean)

    for nid, name_patterns in MN_TARGETS.items():
        match_row = None
        for row in rows:
            school = (row.get("School Name") or "").strip()
            grp_keys = [k for k in row.keys() if k and "Student Group" in k]
            group = (row.get(grp_keys[0]) if grp_keys else "") or ""
            group = group.strip()
            if any(school == p or school.startswith(p) for p in name_patterns) and group == "All Students":
                match_row = row
                break

        rec = load_school(nid)
        rec["accountability"]["year"] = YEAR

        if match_row:
            math_ach = safe_float(match_row.get("Stage 1: Math Ach"))
            reading_ach = safe_float(match_row.get("Stage 1: Reading Ach"))
            if math_ach is not None and reading_ach is not None:
                rec["accountability"]["state_percentile_rank"] = round((math_ach + reading_ach) / 2.0, 1)
            rec["accountability"]["state_rating"] = "Identified for Support"
            label = f"Identified  MathAch={math_ach}  ReadingAch={reading_ach}"
        else:
            # Not in the support-identification file = in good standing under ESSA / North Star
            rec["accountability"]["state_rating"] = "Not Identified (Good Standing)"
            label = "Not Identified"

        save_school(nid, rec)
        print(f"  {nid} {name_patterns[0][:50]:50}  {label}")


# ---------------------------------------------------------------------------

def enrich_minnesota_graduation() -> None:
    """Pull MN graduation rates from the grad indicators file."""
    print("\n=== MINNESOTA graduation ===")
    path = RAW / "MN" / "mn_mca_graduation_indicators_2023-24.csv"
    if not path.exists():
        print(f"  SKIP: {path}")
        return
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    hdr_idx = next((i for i, r in enumerate(rows) if any('District\nName' in (c or '') for c in r)), None)
    if hdr_idx is None:
        print("  Header not found")
        return
    # column indices from header inspection
    SCHOOL, GROUP, ENDING, FOUR_PCT, FIVE_PCT, SIX_PCT = 7, 12, 13, 16, 19, 22

    for nid, name_patterns in MN_TARGETS.items():
        match = None
        for r in rows[hdr_idx+1:]:
            if len(r) <= SIX_PCT: continue
            s = (r[SCHOOL] or "").strip()
            if any(s == p for p in name_patterns):
                if (r[GROUP] or "").strip() == "All Students" and (r[ENDING] or "").strip() == "Graduate":
                    match = r
                    break
        if not match:
            print(f"  {nid}: no graduation row (likely not a high school)")
            continue
        rec = load_school(nid)
        rec["graduation"]["year"] = YEAR
        rec["graduation"]["four_year_grad_rate"] = safe_float(match[FOUR_PCT])
        rec["graduation"]["five_year_grad_rate"] = safe_float(match[FIVE_PCT])
        save_school(nid, rec)
        print(f"  {nid}  4yr={match[FOUR_PCT]}%  5yr={match[FIVE_PCT]}%")


def enrich_minnesota_demographics() -> None:
    """Pull MN race/ELL/FRL counts and percentages from MMR file's subgroup rows."""
    print("\n=== MINNESOTA demographics ===")
    path = RAW / "MN" / "mn_mca_mmr_accountability_2023-24.csv"
    if not path.exists():
        return
    import io as _io
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()
    header_idx = next((i for i, ln in enumerate(lines) if ln.startswith("Year,District Number")), None)
    if header_idx is None: return
    body = "".join(lines[header_idx:])
    rows = []
    for r in csv.DictReader(_io.StringIO(body)):
        clean = {(k.replace("\n", " ").strip() if k else k): v for k, v in r.items()}
        rows.append(clean)

    # For each target, find subgroup rows with their Count fields (eg "Stage 1: Math Ach Count")
    # which represent number of students in that subgroup
    GROUP_KEY = next((k for k in rows[0].keys() if k and 'Student Group' in k), 'Student Group')

    for nid, name_patterns in MN_TARGETS.items():
        rec = load_school(nid)
        total_n = 0
        race_n = {"black": 0}
        ell_n = 0
        frl_n = 0
        for r in rows:
            school = (r.get("School Name") or "").strip()
            if not any(school == p for p in name_patterns):
                continue
            group = (r.get(GROUP_KEY) or "").strip()
            # Use the highest count across stages as the group size proxy
            counts = [safe_float(r.get(k)) for k in r.keys() if k and "Count" in k and "Cohort" not in k]
            counts = [c for c in counts if c is not None]
            if not counts: continue
            n = max(counts)
            if group == "All Students":
                total_n = max(total_n, n)
            elif "Black" in group:
                race_n["black"] = max(race_n["black"], int(n))
            elif "English Learner" in group:
                ell_n = max(ell_n, int(n))
            elif "Free/Reduced" in group:
                frl_n = max(frl_n, int(n))

        if total_n > 0:
            rec["enrollment"]["pct_ell"] = round(100 * ell_n / total_n, 1) if ell_n else None
            rec["enrollment"]["pct_free_reduced_lunch"] = round(100 * frl_n / total_n, 1) if frl_n else None
            # Black race count (other races not in this file)
            rec["enrollment"]["by_race_ethnicity"]["black"] = race_n["black"] if race_n["black"] else None
            save_school(nid, rec)
            print(f"  {nid}  Total_N={int(total_n)}  Black={race_n['black']}  ELL%={rec['enrollment']['pct_ell']}  FRL%={rec['enrollment']['pct_free_reduced_lunch']}")
        else:
            print(f"  {nid}: no MMR rows (school not identified for support; demographics not in this file)")


def main() -> None:
    enrich_illinois()
    enrich_missouri()
    enrich_michigan()
    enrich_michigan_graduation()
    enrich_minnesota()
    enrich_minnesota_graduation()
    enrich_minnesota_demographics()
    print("\nDone. Re-run scripts/10_aggregate.py.")


if __name__ == "__main__":
    main()
