"""
Script 06: Fetch Illinois ISBE data — IAR/PSAT/SAT proficiency, SGP growth, accountability.

Primary sources:
  - Illinois Report Card API: https://www.illinoisreportcard.com
  - ISBE bulk data: https://www.isbe.net/Pages/Illinois-State-Report-Card-Data.aspx

Illinois schools: Chicago Math and Science Academy, Horizon Science Academy Belmont,
  McKinley Park, Southwest Chicago.
"""


from __future__ import annotations
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    SESSION, get_json, load_master, log,
    print_summary, save_school, update_manifest_school,
)

IL_STATE = "IL"
YEAR = "2022-23"

# Illinois Report Card API
IL_RC_API = "https://www.illinoisreportcard.com/api/"
# ISBE bulk data download page
ISBE_BULK_URL = "https://www.isbe.net/Pages/Illinois-State-Report-Card-Data.aspx"
# Direct CSV download attempts
IL_IAR_CSV = "https://www.isbe.net/Documents/RC23_SchoolAssessment.xlsx"
IL_IAR_CSV_ALT = "https://illinoisreportcard.com/api/school/assessments"

MANUAL_URL = ISBE_BULK_URL


def try_il_rc_api(rcdts: str | None = None, school_name: str = "") -> dict | None:
    """Load IL assessment data — local file first, then API fallback.
    Place IAR/PSAT/SAT CSV from isbe.net into data/raw/IL/
    """
    from utils import load_raw_csv
    local = load_raw_csv("IL", "iar") or load_raw_csv("IL", "assessment") or load_raw_csv("IL")
    if local:
        return {"results": local}
    if not rcdts:
        return None
    for url in [
        f"https://www.illinoisreportcard.com/api/school/{rcdts}/assessments/",
        f"https://api.illinoisreportcard.com/school/{rcdts}/",
    ]:
        data = get_json(url)
        if data:
            return data
    return None


def get_il_rcdts(nces_id: str) -> str | None:
    """Get Illinois RCDTS (state ID) from CCD directory."""
    url = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{nces_id}/"
    data = get_json(url)
    if not data or not data.get("results"):
        return None
    results = sorted(data["results"], key=lambda r: r.get("year", 0), reverse=True)
    if results:
        return results[0].get("seasch")
    return None


def process_il_schools(schools: list) -> tuple[int, int, int]:
    il_schools = [s for s in schools if s.get("state") == IL_STATE and s.get("nces_id")]
    updated = failed = 0

    for school in il_schools:
        nces_id = school["nces_id"]
        name = school["school_name"]
        flags = []
        log.info("Processing IL: %s", name)

        rcdts = get_il_rcdts(nces_id)
        if rcdts:
            log.info("IL RCDTS for %s: %s", name, rcdts)

        il_data = try_il_rc_api(rcdts, name)
        ela_pct = None
        math_pct = None

        if il_data:
            # Parse whatever structure comes back
            results = il_data.get("results") or il_data.get("data") or []
            if isinstance(results, list):
                for r in results:
                    subject = (r.get("subject") or r.get("Subject") or "").lower()
                    pct = r.get("pctProficient") or r.get("percentProficient") or r.get("pct_proficient")
                    if pct is not None:
                        try:
                            pct_f = float(pct)
                            if "ela" in subject or "english" in subject or "reading" in subject:
                                ela_pct = pct_f
                            elif "math" in subject:
                                math_pct = pct_f
                        except (ValueError, TypeError):
                            pass

        record = {
            "assessment": {
                "year": YEAR,
                "source": "Illinois IAR / PSAT / SAT (ISBE)",
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
                "science": {"pct_proficient_all": None},
            },
            "growth": {
                "year": YEAR,
                "source": "Illinois ISBE",
                "metric_name": "Student Growth Percentile (SGP)",
                "ela_growth": None,
                "math_growth": None,
                "overall_growth_rating": None,
            },
            "accountability": {
                "year": YEAR,
                "state_rating": None,  # ISBE Summative Designation
                "state_percentile_rank": None,
                "similar_schools_percentile": None,
            },
        }

        status = "ok" if (ela_pct is not None or math_pct is not None) else "needs_manual_download"
        if status == "needs_manual_download":
            flags.append("Illinois ISBE data requires manual download from report card portal")

        update_manifest_school(nces_id, name, IL_STATE, "state_assessment",
                               status=status, year=YEAR,
                               manual_url=MANUAL_URL if status != "ok" else None,
                               flags=flags if flags else None)
        update_manifest_school(nces_id, name, IL_STATE, "state_growth",
                               status="needs_manual_download", year=YEAR,
                               manual_url="https://www.isbe.net/Pages/Illinois-State-Report-Card-Data.aspx")
        update_manifest_school(nces_id, name, IL_STATE, "state_accountability",
                               status="needs_manual_download", year=YEAR,
                               manual_url=MANUAL_URL)

        save_school(nces_id, record)
        updated += 1

    return updated, 0, failed


def main():
    from utils import load_master
    schools = load_master()
    updated, skipped, failed = process_il_schools(schools)
    print_summary("06_fetch_il", updated, skipped, failed)


if __name__ == "__main__":
    main()
