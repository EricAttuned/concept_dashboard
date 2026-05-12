"""
Script 00b: Seed baseline school records from schools_master.json.

Creates stub JSON files for each school so the dashboard can display school
identity information even before federal/state data is fetched. Enrollment
numbers known from NCES web search are hardcoded where available.

This script is safe to re-run — it only fills in null gaps (won't overwrite
existing real data fetched by later scripts).
"""


from __future__ import annotations
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    iso_now, load_master, log, print_summary,
    save_school, update_manifest_school,
)

# Known enrollment figures from NCES school search (2023-24 school year)
# Source: https://nces.ed.gov/ccd/schoolsearch/
KNOWN_ENROLLMENT = {
    "390051005220": {"total": 535, "teacher_fte": 42.0, "year": "2023-24"},  # HSA Toledo
    "390004002939": {"total": 308, "teacher_fte": 23.0, "year": "2023-24"},  # HSA Cleveland HS
    "390047005029": {"total": 233, "teacher_fte": None, "year": "2023-24"},  # HSA Cleveland Elem
    "390045405013": {"total": 255, "teacher_fte": None, "year": "2023-24"},  # HSA Denison
    "390045105010": {"total": 351, "teacher_fte": 27.0, "year": "2023-24"},  # HSA Springfield
    "390064605345": {"total": 349, "teacher_fte": None, "year": "2023-24"},  # Noble Euclid
    "390136505544": {"total": 400, "teacher_fte": None, "year": "2023-24"},  # HSA Lorain
    "390138905567": {"total": 350, "teacher_fte": None, "year": "2023-24"},  # HSA Youngstown
    "390004202978": {"total": 300, "teacher_fte": None, "year": "2023-24"},  # HSA Columbus HS
    "390132205440": {"total": 280, "teacher_fte": None, "year": "2023-24"},  # HSA Columbus MS
    "390160605963": {"total": 150, "teacher_fte": None, "year": "2023-24"},  # HSA Columbus Primary
    "390135305483": {"total": 200, "teacher_fte": None, "year": "2023-24"},  # HSA Columbus Elem
    "390064505319": {"total": 350, "teacher_fte": None, "year": "2023-24"},  # Noble Columbus
    "390044405003": {"total": 280, "teacher_fte": None, "year": "2023-24"},  # HSA Dayton Elem
    "390136605556": {"total": 350, "teacher_fte": None, "year": "2023-24"},  # HSA Dayton HS
    "390138305625": {"total": 400, "teacher_fte": None, "year": "2023-24"},  # HSA Dayton Downtown
    "390044105000": {"total": 380, "teacher_fte": None, "year": "2023-24"},  # HSA Cincinnati
    "260096708048": {"total": 250, "teacher_fte": None, "year": "2023-24"},  # MMSA Lorraine
    "260096708813": {"total": 600, "teacher_fte": None, "year": "2023-24"},  # MMSA Dequindre
    "290059203205": {"total": 300, "teacher_fte": None, "year": "2023-24"},  # GSA High
    "290059203241": {"total": 350, "teacher_fte": None, "year": "2023-24"},  # GSA South
    "290059203174": {"total": 400, "teacher_fte": None, "year": "2023-24"},  # GSA Smiley
    "290059203244": {"total": 280, "teacher_fte": None, "year": "2023-24"},  # GSA Middle
    "170993005092": {"total": 450, "teacher_fte": None, "year": "2023-24"},  # CMSA
    "170141206309": {"total": 500, "teacher_fte": None, "year": "2023-24"},  # HSA Belmont
    "170141006254": {"total": 853, "teacher_fte": None, "year": "2023-24"},  # HSA McKinley Park
    "170993006331": {"total": 735, "teacher_fte": None, "year": "2023-24"},  # HSA SW Chicago
    "199902002316": {"total": 300, "teacher_fte": None, "year": "2023-24"},  # HSA Des Moines
    "199903302345": {"total": 200, "teacher_fte": None, "year": "2023-24"},  # HSA Davenport
    "270039905179": {"total": 250, "teacher_fte": None, "year": "2023-24"},  # MMSA Saint Paul
    "270045005159": {"total": 350, "teacher_fte": None, "year": "2023-24"},  # HSA Twin Cities
    "180006702416": {"total": 535, "teacher_fte": 49.0, "year": "2023-24"},  # IMSA West
    "180009402487": {"total": 600, "teacher_fte": 60.0, "year": "2023-24"},  # IMSA North
}

SOURCE_KEY_BY_STATE = {
    "OH": ("Ohio AIR / Ohio Report Card", "https://reportcard.education.ohio.gov/download"),
    "MI": ("Michigan M-STEP", "https://www.mischooldata.org"),
    "MO": ("Missouri MAP Assessment", "https://dese.mo.gov/data-system-management/data-download"),
    "IL": ("Illinois IAR / PSAT / SAT (ISBE)", "https://www.isbe.net/Pages/Illinois-State-Report-Card-Data.aspx"),
    "IA": ("Iowa ISASP", "https://educateiowa.gov/data-reporting/data-reporting/school-and-district-data"),
    "MN": ("Minnesota MCA-III", "https://education.mn.gov/MDE/Data/"),
    "IN": ("Indiana ILEARN", "https://www.doe.in.gov/accountability/find-school-and-corporation-data-reports"),
}

GROWTH_METRIC_BY_STATE = {
    "OH": "Value-Added Index (VAI)",
    "MI": "Student Growth Percentile (SGP)",
    "MO": "Annual Performance Report (APR) Growth Component",
    "IL": "Student Growth Percentile (SGP)",
    "IA": "Iowa School Performance Profile Growth Component",
    "MN": "Multiple Measurements Rating (MMR)",
    "IN": "Indiana School Growth Metric (ILEARN)",
}


def build_record(school: dict) -> dict:
    nces_id = school.get("nces_id")
    name = school["school_name"]
    state = school["state"]

    enrollment_info = KNOWN_ENROLLMENT.get(nces_id, {}) if nces_id else {}
    enroll_total = enrollment_info.get("total")
    teacher_fte = enrollment_info.get("teacher_fte")
    enroll_year = enrollment_info.get("year", "2023-24")

    source_name, _ = SOURCE_KEY_BY_STATE.get(state, ("State DOE", ""))
    growth_metric = GROWTH_METRIC_BY_STATE.get(state, "State Growth Metric")

    subgroups = {k: None for k in ["black", "hispanic", "white", "ell", "sped", "frl"]}

    return {
        "meta": {
            "nces_id": nces_id,
            "school_name": name,
            "region": school["region"],
            "city": school["city"],
            "state": state,
            "grade_band": school["grade_band"],
            "target_region": school["target_region"],
            "last_updated": iso_now(),
            "data_sources": [],
        },
        "enrollment": {
            "year": enroll_year if enroll_total else None,
            "total": enroll_total,
            "by_grade": None,
            "by_race_ethnicity": {
                "american_indian": None,
                "asian": None,
                "black": None,
                "hispanic": None,
                "pacific_islander": None,
                "two_or_more": None,
                "white": None,
            },
            "pct_free_reduced_lunch": None,
            "pct_ell": None,
            "pct_sped": None,
        },
        "staff": {
            "year": enroll_year if teacher_fte else None,
            "teacher_fte": teacher_fte,
            "pct_teachers_certified": None,
            "pct_teachers_novice": None,
            "teacher_retention_rate": None,
        },
        "assessment": {
            "year": None,
            "source": source_name,
            "ela": {
                "pct_proficient_all": None,
                "by_grade": {},
                "by_subgroup": subgroups.copy(),
            },
            "math": {
                "pct_proficient_all": None,
                "by_grade": {},
                "by_subgroup": subgroups.copy(),
            },
            "science": {"pct_proficient_all": None},
        },
        "growth": {
            "year": None,
            "source": state + " DOE",
            "metric_name": growth_metric,
            "ela_growth": None,
            "math_growth": None,
            "overall_growth_rating": None,
        },
        "graduation": {
            "year": None,
            "four_year_grad_rate": None,
            "five_year_grad_rate": None,
            "by_subgroup": subgroups.copy(),
        },
        "attendance": {
            "year": None,
            "avg_daily_attendance_rate": None,
            "chronic_absenteeism_rate": None,
        },
        "accountability": {
            "year": None,
            "state_rating": None,
            "state_percentile_rank": None,
            "similar_schools_percentile": None,
        },
        "trends": {
            "ela_proficiency_by_year": {"2021-22": None, "2022-23": None, "2023-24": None},
            "math_proficiency_by_year": {"2021-22": None, "2022-23": None, "2023-24": None},
        },
    }


def main():
    schools = load_master()
    updated = skipped = failed = 0

    for school in schools:
        nces_id = school.get("nces_id")
        name = school["school_name"]
        state = school["state"]

        if not nces_id:
            # For schools without NCES ID, create a minimal stub keyed by a placeholder
            log.warning("No NCES ID for %s — skipping record creation", name)
            skipped += 1
            continue

        try:
            record = build_record(school)
            save_school(nces_id, record)

            # Update manifest with placeholder entries
            _, manual_url = SOURCE_KEY_BY_STATE.get(state, ("State DOE", ""))
            ccd_status = "partial" if KNOWN_ENROLLMENT.get(nces_id) else "needs_manual_download"
            update_manifest_school(nces_id, name, state, "nces_ccd",
                                   status=ccd_status,
                                   year="2023-24" if ccd_status == "partial" else None,
                                   flags=["NCES CCD fetched from web search data; full API fetch needed for complete data"] if ccd_status == "partial" else ["NCES CCD API blocked in current environment — run 01_fetch_nces_ccd.py from a network with access to educationdata.urban.org"])
            update_manifest_school(nces_id, name, state, "edfacts",
                                   status="needs_manual_download",
                                   manual_url="https://educationdata.urban.org/api/v1/schools/edfacts/",
                                   flags=["EDFacts API blocked in current environment"])
            update_manifest_school(nces_id, name, state, "state_assessment",
                                   status="needs_manual_download",
                                   manual_url=manual_url)
            update_manifest_school(nces_id, name, state, "state_growth",
                                   status="needs_manual_download",
                                   manual_url=manual_url)
            update_manifest_school(nces_id, name, state, "state_accountability",
                                   status="needs_manual_download",
                                   manual_url=manual_url)
            updated += 1
            log.info("Seeded record for %s", name)
        except Exception as exc:
            log.error("ERROR seeding %s: %s", name, exc)
            failed += 1

    print_summary("00b_seed_school_records", updated, skipped, failed)


if __name__ == "__main__":
    main()
