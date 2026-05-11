"""
Script 07: Fetch Iowa DOE data — ISASP proficiency, Iowa School Performance Profile.

Primary source:
  - Iowa DE data: https://educateiowa.gov/data-reporting/data-reporting/school-and-district-data
  - ISASP results CSV downloads

Iowa schools: Horizon Science Academy Des Moines, Horizon Science Academy Davenport.
"""

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    SESSION, load_master, log,
    print_summary, save_school, update_manifest_school,
)

IA_STATE = "IA"
YEAR = "2022-23"

# Iowa DE public data download URLs
IA_ISASP_URL = "https://educateiowa.gov/sites/files/ed/documents/ISASP_School_2023.csv"
IA_ISASP_ALT = "https://educateiowa.gov/data-reporting/data-reporting/school-and-district-data"

MANUAL_URL = IA_ISASP_ALT


def try_fetch_ia_isasp() -> list[dict] | None:
    """Load Iowa ISASP data — local file first, then URL fallback.
    Place the ISASP CSV from educateiowa.gov into data/raw/IA/
    """
    from utils import load_raw_csv
    local = load_raw_csv("IA", "isasp") or load_raw_csv("IA", "ISASP") or load_raw_csv("IA")
    if local:
        return local
    for url in [
        IA_ISASP_URL,
        "https://educateiowa.gov/sites/files/ed/documents/2022-2023_ISASP_School_Building_Results.csv",
    ]:
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "csv" in ct or url.endswith(".csv"):
                text = r.content.decode("utf-8-sig", errors="replace")
                rows = list(csv.DictReader(io.StringIO(text)))
                if rows:
                    log.info("IA: Downloaded ISASP data (%d rows)", len(rows))
                    return rows
        except Exception as exc:
            log.warning("IA: URL %s failed: %s", url, exc)
    return None


def match_ia_school(rows: list[dict], name: str) -> list[dict]:
    name_lower = name.lower()
    keywords = []
    if "des moines" in name_lower:
        keywords = ["horizon science", "des moines"]
    elif "davenport" in name_lower:
        keywords = ["horizon science", "davenport"]
    return [
        r for r in rows
        if all(k in (r.get("School Name") or r.get("SCHOOL_NAME") or "").lower() for k in keywords)
    ]


def process_ia_schools(schools: list) -> tuple[int, int, int]:
    ia_schools = [s for s in schools if s.get("state") == IA_STATE and s.get("nces_id")]
    updated = failed = 0

    ia_data = try_fetch_ia_isasp()

    for school in ia_schools:
        nces_id = school["nces_id"]
        name = school["school_name"]
        flags = []
        log.info("Processing IA: %s", name)

        ela_pct = None
        math_pct = None
        sci_pct = None

        if ia_data:
            school_rows = match_ia_school(ia_data, name)
            for r in school_rows:
                subject = (r.get("Subject") or r.get("SUBJECT") or "").lower()
                pct = r.get("Percent Proficient") or r.get("PCT_PROF") or r.get("Pct Prof")
                if pct is not None:
                    try:
                        pct_f = float(str(pct).replace("%", "").strip())
                        if "ela" in subject or "english" in subject or "reading" in subject:
                            ela_pct = pct_f
                        elif "math" in subject:
                            math_pct = pct_f
                        elif "science" in subject:
                            sci_pct = pct_f
                    except (ValueError, TypeError):
                        pass

        record = {
            "assessment": {
                "year": YEAR,
                "source": "Iowa ISASP",
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
                "source": "Iowa DE",
                "metric_name": "Iowa School Performance Profile Growth Component",
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
            flags.append("Iowa ISASP data requires manual download from Iowa DE portal")

        update_manifest_school(nces_id, name, IA_STATE, "state_assessment",
                               status=status, year=YEAR,
                               manual_url=MANUAL_URL if status != "ok" else None,
                               flags=flags if flags else None)
        update_manifest_school(nces_id, name, IA_STATE, "state_growth",
                               status="needs_manual_download", year=YEAR,
                               manual_url="https://educateiowa.gov/data-reporting/data-reporting/school-and-district-data")
        update_manifest_school(nces_id, name, IA_STATE, "state_accountability",
                               status="needs_manual_download", year=YEAR,
                               manual_url=MANUAL_URL)

        save_school(nces_id, record)
        updated += 1

    return updated, 0, failed


def main():
    from utils import load_master
    schools = load_master()
    updated, skipped, failed = process_ia_schools(schools)
    print_summary("07_fetch_ia", updated, skipped, failed)


if __name__ == "__main__":
    main()
