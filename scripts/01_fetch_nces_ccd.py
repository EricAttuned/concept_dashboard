"""
Script 01: Fetch NCES CCD data (enrollment, staff) for all Concept Schools.

Endpoints used (Urban Institute Education Data Portal):
  GET /schools/ccd/directory/{ncessch}/      → locale, charter flag, FRL
  GET /schools/ccd/enrollment/{ncessch}/race/ → enrollment by race/ethnicity
  GET /schools/ccd/enrollment/{ncessch}/grade/ → enrollment by grade
  GET /schools/ccd/staff/{ncessch}/          → teacher FTE
"""


from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    get_json, iso_now, load_master, log, nces_val,
    print_summary, save_school, update_manifest_school, year_label,
)

BASE = "https://educationdata.urban.org/api/v1"

RACE_MAP = {
    "white": "white",
    "black": "black",
    "hispanic": "hispanic",
    "asian": "asian",
    "american_indian_alaska_native": "american_indian",
    "native_hawaiian_pacific_islander": "pacific_islander",
    "two_or_more_races": "two_or_more",
}


def fetch_directory(ncessch: str) -> dict | None:
    url = f"{BASE}/schools/ccd/directory/{ncessch}/"
    data = get_json(url)
    if not data or not data.get("results"):
        return None
    # Results is a list; take the most recent year
    results = sorted(data["results"], key=lambda r: r.get("year", 0), reverse=True)
    return results[0] if results else None


def fetch_enrollment_race(ncessch: str) -> list:
    url = f"{BASE}/schools/ccd/enrollment/{ncessch}/race/"
    data = get_json(url)
    if not data:
        return []
    return data.get("results", [])


def fetch_enrollment_grade(ncessch: str) -> list:
    url = f"{BASE}/schools/ccd/enrollment/{ncessch}/grade/"
    data = get_json(url)
    if not data:
        return []
    return data.get("results", [])


def fetch_staff(ncessch: str) -> list:
    url = f"{BASE}/schools/ccd/staff/{ncessch}/"
    data = get_json(url)
    if not data:
        return []
    return data.get("results", [])


def most_recent_year(records: list, year_field: str = "year") -> int | None:
    years = [r.get(year_field) for r in records if r.get(year_field)]
    return max(years) if years else None


def process_school(school: dict) -> bool:
    nces_id = school.get("nces_id")
    name = school["school_name"]
    state = school["state"]

    if not nces_id:
        log.warning("Skipping %s — no NCES ID", name)
        return False

    log.info("Fetching CCD: %s (%s)", name, nces_id)

    # ── Directory ────────────────────────────────────────────────
    directory = fetch_directory(nces_id)
    flags = []

    # ── Enrollment by race ───────────────────────────────────────
    race_records = fetch_enrollment_race(nces_id)
    most_yr = most_recent_year(race_records)
    race_year_records = [r for r in race_records if r.get("year") == most_yr]

    by_race = {v: None for v in RACE_MAP.values()}
    total_enrollment = None

    for r in race_year_records:
        race_raw = (r.get("race_ethnicity") or "").lower().replace(" ", "_").replace("/", "_")
        enrollment = nces_val(r.get("enrollment"))
        if race_raw in RACE_MAP:
            mapped = RACE_MAP[race_raw]
            by_race[mapped] = int(enrollment) if enrollment is not None else None
        if (r.get("race_ethnicity") or "").lower() in ("total", "all students"):
            total_enrollment = int(enrollment) if enrollment is not None else None

    # Compute total from sum if not found directly
    if total_enrollment is None:
        parts = [v for v in by_race.values() if v is not None]
        if parts:
            total_enrollment = sum(parts)

    # Check suppression
    if any(v is None for v in by_race.values()):
        flags.append("Some race/ethnicity enrollment counts suppressed by NCES")

    # ── Enrollment by grade ──────────────────────────────────────
    grade_records = fetch_enrollment_grade(nces_id)
    grade_yr = most_recent_year(grade_records)
    grade_year_records = [r for r in grade_records if r.get("year") == grade_yr]

    by_grade = {}
    for r in grade_year_records:
        grade = r.get("grade")
        enroll = nces_val(r.get("enrollment"))
        if grade and enroll is not None:
            # Standardize grade label
            grade_label = str(grade).zfill(2) if str(grade).isdigit() else str(grade)
            by_grade[grade_label] = int(enroll)

    # ── Staff ────────────────────────────────────────────────────
    staff_records = fetch_staff(nces_id)
    staff_yr = most_recent_year(staff_records)
    staff_year_records = [r for r in staff_records if r.get("year") == staff_yr]

    teacher_fte = None
    for r in staff_year_records:
        staff_type = (r.get("staff_category") or "").lower()
        if "teacher" in staff_type:
            fte = nces_val(r.get("fte"))
            if fte is not None:
                teacher_fte = float(fte)
                break

    # ── FRL from directory ───────────────────────────────────────
    pct_frl = None
    if directory:
        frl_eligible = nces_val(directory.get("frl_eligible"))
        enroll_dir = nces_val(directory.get("enrollment"))
        if frl_eligible is not None and enroll_dir and float(enroll_dir) > 0:
            pct_frl = round(float(frl_eligible) / float(enroll_dir) * 100, 1)
        elif frl_eligible is not None:
            pct_frl = None
            flags.append("FRL percentage could not be computed — enrollment missing from directory")

    # ── Determine year label ─────────────────────────────────────
    yr = most_yr or (directory.get("year") if directory else None)
    yr_label = year_label(int(yr)) if yr else None

    # ── Assemble record ──────────────────────────────────────────
    record = {
        "meta": {
            "nces_id": nces_id,
            "school_name": name,
            "region": school["region"],
            "city": school["city"],
            "state": state,
            "grade_band": school["grade_band"],
            "target_region": school["target_region"],
            "last_updated": iso_now(),
            "data_sources": ["NCES CCD"],
        },
        "enrollment": {
            "year": yr_label,
            "total": total_enrollment,
            "by_grade": by_grade or None,
            "by_race_ethnicity": by_race,
            "pct_free_reduced_lunch": pct_frl,
            "pct_ell": None,
            "pct_sped": None,
        },
        "staff": {
            "year": year_label(int(staff_yr)) if staff_yr else None,
            "teacher_fte": teacher_fte,
            "pct_teachers_certified": None,
            "pct_teachers_novice": None,
            "teacher_retention_rate": None,
        },
    }

    save_school(nces_id, record)
    status = "ok" if total_enrollment else "partial"
    update_manifest_school(
        nces_id, name, state, "nces_ccd",
        status=status,
        year=yr_label,
        flags=flags if flags else None,
    )
    return True


def main():
    schools = load_master()
    if not schools:
        log.error("No schools in master list — run 00_build_master_list.py first")
        sys.exit(1)

    updated = skipped = failed = 0
    for school in schools:
        try:
            ok = process_school(school)
            if ok:
                updated += 1
            else:
                skipped += 1
        except Exception as exc:
            log.error("ERROR processing %s: %s", school.get("school_name"), exc)
            failed += 1

    print_summary("01_fetch_nces_ccd", updated, skipped, failed)


if __name__ == "__main__":
    main()
