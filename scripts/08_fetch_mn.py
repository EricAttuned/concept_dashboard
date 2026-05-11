"""
Script 08: Fetch Minnesota MDE data — MCA proficiency, MMR growth, accountability.

Primary source:
  - MDE Data: https://education.mn.gov/MDE/Data/
  - MCA results: https://education.mn.gov/MDE/fam/tests/mca/

Target schools:
  - Minnesota Math and Science Academy (Saint Paul, MN)
  - Horizon Science Academy Twin Cities (Minneapolis, MN)
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

MN_STATE = "MN"
YEAR = "2022-23"

MN_MCA_URL = "https://education.mn.gov/mdeprod/groups/EdDev/documents/Basic_Package/bwrl/MDEFiles/2023_MCA_School_Level_Data.csv"
MN_MANUAL_URL = "https://education.mn.gov/MDE/Data/"


def try_fetch_mn_mca() -> list[dict] | None:
    """Load Minnesota MCA data — local file first, then URL fallback.
    Place the MCA CSV from education.mn.gov/MDE/Data/ into data/raw/MN/
    """
    from utils import load_raw_csv
    local = load_raw_csv("MN", "mca") or load_raw_csv("MN", "MCA") or load_raw_csv("MN")
    if local:
        return local
    for url in [
        MN_MCA_URL,
        "https://education.mn.gov/mdeprod/groups/EdDev/documents/Basic_Package/bwrl/MDEFiles/MCA_2023_Schools.csv",
    ]:
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "csv" in ct or url.endswith(".csv"):
                text = r.content.decode("utf-8-sig", errors="replace")
                rows = list(csv.DictReader(io.StringIO(text)))
                if rows:
                    log.info("MN: Downloaded MCA data (%d rows)", len(rows))
                    return rows
        except Exception as exc:
            log.warning("MN: URL %s failed: %s", url, exc)
    return None


def match_mn_school(rows: list[dict], name: str) -> list[dict]:
    name_lower = name.lower()
    matches = []
    for r in rows:
        sname = (r.get("School Name") or r.get("SCHOOL_NAME") or "").lower()
        if "minnesota math and science" in name_lower and "minnesota math" in sname:
            matches.append(r)
        elif "horizon science" in name_lower and "twin cities" in name_lower and "horizon" in sname and "twin" in sname:
            matches.append(r)
    return matches


def process_mn_schools(schools: list) -> tuple[int, int, int]:
    mn_schools = [s for s in schools if s.get("state") == MN_STATE and s.get("nces_id")]
    updated = failed = 0

    mn_data = try_fetch_mn_mca()

    for school in mn_schools:
        nces_id = school["nces_id"]
        name = school["school_name"]
        flags = []
        log.info("Processing MN: %s", name)

        ela_pct = None
        math_pct = None
        sci_pct = None

        if mn_data:
            school_rows = match_mn_school(mn_data, name)
            for r in school_rows:
                subject = (r.get("Subject") or r.get("SUBJECT") or "").lower()
                pct = r.get("Percent Proficient") or r.get("PCT_PROF") or r.get("Pct Proficient")
                if pct is not None:
                    try:
                        pct_f = float(str(pct).replace("%", "").strip())
                        if "reading" in subject or "ela" in subject or "english" in subject:
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
                "source": "Minnesota MCA-III",
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
                "source": "Minnesota MDE",
                "metric_name": "Multiple Measurements Rating (MMR)",
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
            flags.append("Minnesota MCA data requires manual download from MDE portal")

        update_manifest_school(nces_id, name, MN_STATE, "state_assessment",
                               status=status, year=YEAR,
                               manual_url=MN_MANUAL_URL if status != "ok" else None,
                               flags=flags if flags else None)
        update_manifest_school(nces_id, name, MN_STATE, "state_growth",
                               status="needs_manual_download", year=YEAR,
                               manual_url="https://education.mn.gov/MDE/Data/")
        update_manifest_school(nces_id, name, MN_STATE, "state_accountability",
                               status="needs_manual_download", year=YEAR,
                               manual_url=MN_MANUAL_URL)

        save_school(nces_id, record)
        updated += 1

    return updated, 0, failed


def main():
    from utils import load_master
    schools = load_master()
    updated, skipped, failed = process_mn_schools(schools)
    print_summary("08_fetch_mn", updated, skipped, failed)


if __name__ == "__main__":
    main()
