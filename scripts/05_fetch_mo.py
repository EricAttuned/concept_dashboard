"""
Script 05: Fetch Missouri DESE data — MAP assessment, accountability (APR).

Primary sources:
  - Missouri Assessment Program (MAP): https://dese.mo.gov/data-system-management/data-download
  - Missouri Comprehensive Data System: https://mcds.dese.mo.gov

Gateway Science Academy schools (all in St. Louis, MO).
"""

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    SESSION, get_json, load_master, log,
    print_summary, save_school, update_manifest_school,
)

MO_STATE = "MO"
YEAR = "2022-23"

# Missouri DESE public data download URLs
MO_MAP_URL = "https://dese.mo.gov/sites/default/files/MAP_2023_School_Level_Data.csv"
MO_MAP_URL_ALT = "https://mcds.dese.mo.gov/guidedinquiry/School%20Information/MAP%20Assessment%20Results.aspx"

MANUAL_URL = "https://dese.mo.gov/data-system-management/data-download"
MCDS_URL = "https://mcds.dese.mo.gov"


def try_fetch_mo_map() -> list[dict] | None:
    """Load Missouri MAP data — local file first, then URL fallback.
    Place the MAP CSV from dese.mo.gov or mcds.dese.mo.gov into data/raw/MO/
    """
    from utils import load_raw_csv
    local = load_raw_csv("MO", "map") or load_raw_csv("MO", "MAP") or load_raw_csv("MO")
    if local:
        return local
    try:
        r = SESSION.get(MO_MAP_URL, timeout=30)
        r.raise_for_status()
        text = r.content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if rows:
            log.info("MO: Downloaded MAP data (%d rows)", len(rows))
            return rows
    except Exception as exc:
        log.warning("MO: Primary MAP URL failed: %s", exc)
    return None


def match_school_mo(rows: list[dict], name: str) -> list[dict]:
    """Find rows matching a Missouri school by name."""
    name_lower = name.lower()
    matches = []
    for r in rows:
        school_name = (r.get("School Name") or r.get("SCHOOL_NAME") or "").lower()
        if any(word in school_name for word in ["gateway science", "gateway science academy"]):
            if "smiley" in name_lower and "smiley" in school_name:
                matches.append(r)
            elif "high" in name_lower and ("high" in school_name or "9" in school_name):
                matches.append(r)
            elif "middle" in name_lower and "middle" in school_name:
                matches.append(r)
            elif "south" in name_lower and "south" in school_name:
                matches.append(r)
    return matches


def process_mo_schools(schools: list) -> tuple[int, int, int]:
    mo_schools = [s for s in schools if s.get("state") == MO_STATE and s.get("nces_id")]
    updated = failed = 0

    # Try to download MAP data once for all MO schools
    map_data = try_fetch_mo_map()

    for school in mo_schools:
        nces_id = school["nces_id"]
        name = school["school_name"]
        flags = []
        log.info("Processing MO: %s", name)

        ela_pct = None
        math_pct = None
        sci_pct = None

        if map_data:
            school_rows = match_school_mo(map_data, name)
            for r in school_rows:
                subject = (r.get("Subject") or r.get("SUBJECT") or "").lower()
                pct = r.get("Pct Prof") or r.get("PERCENT_PROFICIENT") or r.get("PCT_PROF")
                if pct is not None:
                    try:
                        pct_f = float(str(pct).replace("%", "").strip())
                        if "communication arts" in subject or "ela" in subject or "english" in subject:
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
                "source": "Missouri MAP Assessment",
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
                "source": "Missouri DESE",
                "metric_name": "Annual Performance Report (APR) Growth Component",
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
            flags.append("Missouri MAP data requires manual download from DESE or MCDS portal")

        update_manifest_school(nces_id, name, MO_STATE, "state_assessment",
                               status=status, year=YEAR,
                               manual_url=MANUAL_URL if status != "ok" else None,
                               flags=flags if flags else None)
        update_manifest_school(nces_id, name, MO_STATE, "state_growth",
                               status="needs_manual_download", year=YEAR,
                               manual_url=MCDS_URL)
        update_manifest_school(nces_id, name, MO_STATE, "state_accountability",
                               status="needs_manual_download", year=YEAR,
                               manual_url=MANUAL_URL)

        save_school(nces_id, record)
        updated += 1

    return updated, 0, failed


def main():
    from utils import load_master
    schools = load_master()
    updated, skipped, failed = process_mo_schools(schools)
    print_summary("05_fetch_mo", updated, skipped, failed)


if __name__ == "__main__":
    main()
