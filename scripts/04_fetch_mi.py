"""
Script 04: Fetch Michigan MDE data — M-STEP proficiency, growth (SGP), accountability.

Primary source: MI School Data at https://www.mischooldata.org
Target schools:
  - Michigan Math and Science Academy Lorraine (Warren, MI) — PreK-5
  - Michigan Math and Science Academy Dequindre (Warren, MI) — PreK-12
  - Horizon Science Academy New Bedford (Lambertville, MI) — PreK-8

MI School Data exports require navigation through a data portal.
This script attempts the public data download endpoints and logs manual steps if needed.
"""

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    SESSION, get_json, iso_now, load_master, log,
    print_summary, save_school, update_manifest_school, year_label,
)

MI_STATE = "MI"
YEAR = "2022-23"

# MI School Data public download endpoints (may require specific request params)
MI_MSTEP_URL = "https://www.mischooldata.org/api/StudentPerformance/GetPerformanceData"

MANUAL_URLS = {
    "assessment": "https://www.mischooldata.org/student-performance/",
    "growth": "https://www.mischooldata.org/student-growth/",
    "accountability": "https://www.mischooldata.org/accountability-scorecard/",
}


def try_fetch_mi_data(nces_id: str, district_code: str | None = None) -> dict | None:
    """
    Attempt to pull M-STEP data from MI School Data API.
    The public portal uses undocumented endpoints; we attempt common patterns.
    """
    params = {
        "schoolYear": "2022-2023",
        "entityType": "School",
        "ncessch": nces_id,
    }
    data = get_json(MI_MSTEP_URL, params=params)
    return data


def get_mi_district_code(nces_id: str) -> str | None:
    """Get Michigan district code from CCD directory."""
    url = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{nces_id}/"
    data = get_json(url)
    if not data or not data.get("results"):
        return None
    results = sorted(data["results"], key=lambda r: r.get("year", 0), reverse=True)
    if results:
        return results[0].get("leaid")
    return None


def process_mi_schools(schools: list) -> tuple[int, int, int]:
    mi_schools = [s for s in schools if s.get("state") == MI_STATE and s.get("nces_id")]
    updated = failed = 0

    for school in mi_schools:
        nces_id = school["nces_id"]
        name = school["school_name"]
        flags = []

        log.info("Processing MI: %s", name)

        # Attempt API fetch
        mi_data = try_fetch_mi_data(nces_id)
        ela_pct = None
        math_pct = None
        sci_pct = None

        if mi_data and isinstance(mi_data, dict):
            results = mi_data.get("results", mi_data.get("data", []))
            if isinstance(results, list):
                for r in results:
                    subject = (r.get("subject") or r.get("Subject") or "").lower()
                    pct = r.get("pctProficient") or r.get("PctProficient")
                    if pct is not None:
                        try:
                            pct = float(pct)
                            if "ela" in subject or "english" in subject or "reading" in subject:
                                ela_pct = pct
                            elif "math" in subject:
                                math_pct = pct
                            elif "science" in subject:
                                sci_pct = pct
                        except (ValueError, TypeError):
                            pass

        record = {
            "assessment": {
                "year": YEAR,
                "source": "Michigan M-STEP",
                "ela": {
                    "pct_proficient_all": ela_pct,
                    "by_grade": {},
                    "by_subgroup": {k: None for k in ["black", "hispanic", "white", "ell", "sped", "frl"]},
                },
                "math": {
                    "pct_proficient_all": math_pct,
                    "by_grade": {},
                    "by_subgroup": {k: None for k in ["black", "hispanic", "white", "ell", "sped", "frl"]},
                },
                "science": {"pct_proficient_all": sci_pct},
            },
            "growth": {
                "year": YEAR,
                "source": "Michigan MDE",
                "metric_name": "Student Growth Percentile (SGP)",
                "ela_growth": None,
                "math_growth": None,
                "overall_growth_rating": None,
            },
            "accountability": {
                "year": YEAR,
                "state_rating": None,
                "state_percentile_rank": None,
                "similar_schools_percentile": None,
            },
        }

        status = "ok" if (ela_pct is not None or math_pct is not None) else "needs_manual_download"
        if status == "needs_manual_download":
            flags.append("MI School Data portal requires manual navigation — automated fetch failed")

        for source_key, manual_url in MANUAL_URLS.items():
            key_map = {
                "assessment": "state_assessment",
                "growth": "state_growth",
                "accountability": "state_accountability",
            }
            update_manifest_school(nces_id, name, MI_STATE, key_map[source_key],
                                   status=status, year=YEAR,
                                   manual_url=manual_url if status == "needs_manual_download" else None,
                                   flags=flags if source_key == "assessment" else None)

        save_school(nces_id, record)
        updated += 1

    return updated, 0, failed


def main():
    from utils import load_master
    schools = load_master()
    updated, skipped, failed = process_mi_schools(schools)
    print_summary("04_fetch_mi", updated, skipped, failed)


if __name__ == "__main__":
    main()
