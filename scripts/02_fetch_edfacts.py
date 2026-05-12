"""
Script 02: Fetch EDFacts data (graduation rates, federal assessment) via Urban Institute.

Endpoints:
  GET /schools/edfacts/grad-rates/{ncessch}/    → 4-year cohort grad rates
  GET /schools/edfacts/assessments/{ncessch}/   → federal proficiency rates

EDFacts typically lags 1-2 years; used as fallback / cross-check vs state data.
"""


from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    get_json, iso_now, load_master, log, nces_val,
    print_summary, save_school, update_manifest_school, year_label,
)

BASE = "https://educationdata.urban.org/api/v1"

SUBGROUP_MAP = {
    "black": "black",
    "hispanic": "hispanic",
    "white": "white",
    "english_language_learners": "ell",
    "students_with_disabilities": "sped",
    "economically_disadvantaged": "frl",
}


def fetch_grad_rates(ncessch: str) -> list:
    url = f"{BASE}/schools/edfacts/grad-rates/{ncessch}/"
    data = get_json(url)
    return (data or {}).get("results", [])


def fetch_assessments(ncessch: str) -> list:
    url = f"{BASE}/schools/edfacts/assessments/{ncessch}/"
    data = get_json(url)
    return (data or {}).get("results", [])


def most_recent(records: list, yr_field: str = "year") -> tuple[int | None, list]:
    years = [r.get(yr_field) for r in records if r.get(yr_field)]
    if not years:
        return None, []
    yr = max(years)
    return yr, [r for r in records if r.get(yr_field) == yr]


def process_school(school: dict) -> bool:
    nces_id = school.get("nces_id")
    name = school["school_name"]
    state = school["state"]

    if not nces_id:
        log.warning("Skipping %s — no NCES ID", name)
        return False

    log.info("Fetching EDFacts: %s (%s)", name, nces_id)
    flags = []

    # ── Graduation rates ─────────────────────────────────────────
    grad_records = fetch_grad_rates(nces_id)
    grad_yr, grad_recent = most_recent(grad_records)

    four_year = None
    five_year = None
    grad_subgroups = {v: None for v in SUBGROUP_MAP.values()}

    for r in grad_recent:
        cohort_type = (r.get("cohort_type") or "").lower()
        grad_rate = nces_val(r.get("graduation_rate"))
        subgroup_raw = (r.get("race_ethnicity") or r.get("subgroup") or "").lower().replace(" ", "_")

        if grad_rate is not None:
            grad_rate = float(grad_rate)
            if "4" in cohort_type or "four" in cohort_type:
                if subgroup_raw in ("all", "total", "all_students", ""):
                    four_year = grad_rate
                elif subgroup_raw in SUBGROUP_MAP:
                    grad_subgroups[SUBGROUP_MAP[subgroup_raw]] = grad_rate
            elif "5" in cohort_type or "five" in cohort_type:
                if subgroup_raw in ("all", "total", "all_students", ""):
                    five_year = grad_rate

    grad_yr_label = year_label(int(grad_yr)) if grad_yr else None

    # ── Assessments ──────────────────────────────────────────────
    assess_records = fetch_assessments(nces_id)
    assess_yr, assess_recent = most_recent(assess_records)
    assess_yr_label = year_label(int(assess_yr)) if assess_yr else None

    ela_all = None
    math_all = None
    ela_subgroups = {v: None for v in SUBGROUP_MAP.values()}
    math_subgroups = {v: None for v in SUBGROUP_MAP.values()}

    for r in assess_recent:
        subject = (r.get("subject") or "").lower()
        subgroup_raw = (r.get("race_ethnicity") or r.get("subgroup") or "all").lower().replace(" ", "_")
        pct = nces_val(r.get("pct_proficient_or_above"))
        if pct is None:
            continue
        pct = float(pct)

        if "ela" in subject or "reading" in subject or "english" in subject:
            if subgroup_raw in ("all", "total", "all_students"):
                ela_all = pct
            elif subgroup_raw in SUBGROUP_MAP:
                ela_subgroups[SUBGROUP_MAP[subgroup_raw]] = pct
        elif "math" in subject:
            if subgroup_raw in ("all", "total", "all_students"):
                math_all = pct
            elif subgroup_raw in SUBGROUP_MAP:
                math_subgroups[SUBGROUP_MAP[subgroup_raw]] = pct

    # Check if EDFacts data is older than state data will be
    if assess_yr and int(assess_yr) < 2022:
        flags.append(f"EDFacts assessment data is from {assess_yr_label} — may be superseded by state data")

    # ── Assemble record ──────────────────────────────────────────
    record = {
        "graduation": {
            "year": grad_yr_label,
            "four_year_grad_rate": four_year,
            "five_year_grad_rate": five_year,
            "by_subgroup": grad_subgroups,
        },
        "assessment": {
            "year": assess_yr_label,
            "source": "EDFacts (federal)",
            "ela": {
                "pct_proficient_all": ela_all,
                "by_grade": {},
                "by_subgroup": ela_subgroups,
            },
            "math": {
                "pct_proficient_all": math_all,
                "by_grade": {},
                "by_subgroup": math_subgroups,
            },
            "science": {"pct_proficient_all": None},
        },
    }

    save_school(nces_id, record)

    assess_status = "ok" if (ela_all is not None or math_all is not None) else "needs_manual_download"
    grad_status = "ok" if four_year is not None else "needs_manual_download"

    update_manifest_school(nces_id, name, state, "edfacts",
                           status=assess_status, year=assess_yr_label, flags=flags if flags else None)
    update_manifest_school(nces_id, name, state, "edfacts_grad",
                           status=grad_status, year=grad_yr_label)
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

    print_summary("02_fetch_edfacts", updated, skipped, failed)


if __name__ == "__main__":
    main()
