"""
Script 03: Fetch Ohio DOE data — Achievement, Progress (Value-Added), Accountability.

Ohio Report Card bulk CSVs:
  https://reportcard.education.ohio.gov/download

Files targeted:
  - Achievement component (ELA/Math proficiency by grade and subgroup)
  - Progress component (Value-Added scores)
  - Gap Closing component (subgroup performance)
  - Overall component grades (A-F accountability)

Schools are matched by Ohio IRN (state_id / seasch field in CCD directory).
"""

import csv
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    SESSION, get_json, iso_now, load_master, log, nces_val,
    print_summary, save_school, update_manifest_school, year_label,
)

BASE_DOWNLOAD = "https://reportcard.education.ohio.gov/download"

# Ohio Report Card bulk download URLs for most recent available year (2022-23)
# These are direct CSV/ZIP links from the Ohio RC download page
OH_DATA_URLS = {
    "achievement": "https://reportcard.education.ohio.gov/api/Download/DownloadFile?fileName=Achievement_2223.xlsx",
    "progress": "https://reportcard.education.ohio.gov/api/Download/DownloadFile?fileName=Progress_2223.xlsx",
    "gap_closing": "https://reportcard.education.ohio.gov/api/Download/DownloadFile?fileName=GapClosing_2223.xlsx",
    "overall": "https://reportcard.education.ohio.gov/api/Download/DownloadFile?fileName=BuildingOverallSummary_2223.xlsx",
}

# Fallback: NCES CCD has seasch (state assigned ID) which is the Ohio IRN
OH_STATE = "OH"
YEAR = "2022-23"


def get_oh_irn(nces_id: str) -> str | None:
    """Look up Ohio IRN from the CCD directory record (seasch field)."""
    url = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{nces_id}/"
    data = get_json(url)
    if not data or not data.get("results"):
        return None
    results = sorted(data["results"], key=lambda r: r.get("year", 0), reverse=True)
    if results:
        return results[0].get("seasch")
    return None


def try_fetch_csv_zip(url: str, filename_hint: str) -> list[dict] | None:
    """Attempt to download a ZIP file and parse the first CSV inside."""
    import requests
    try:
        r = SESSION.get(url, timeout=30)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "zip" in content_type or url.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not csv_names:
                    return None
                with zf.open(csv_names[0]) as cf:
                    text = cf.read().decode("utf-8-sig", errors="replace")
                    reader = csv.DictReader(io.StringIO(text))
                    return list(reader)
        elif "csv" in content_type or url.endswith(".csv"):
            text = r.content.decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            return list(reader)
        else:
            log.warning("OH: Unexpected content type %s for %s", content_type, url)
            return None
    except Exception as exc:
        log.warning("OH: Could not fetch %s: %s", url, exc)
        return None


def process_oh_schools(schools: list) -> tuple[int, int, int]:
    oh_schools = [s for s in schools if s.get("state") == OH_STATE and s.get("nces_id")]

    if not oh_schools:
        return 0, 0, 0

    updated = failed = 0

    # Try to get Ohio IRNs for all OH schools
    irn_map = {}  # nces_id -> irn
    for s in oh_schools:
        irn = get_oh_irn(s["nces_id"])
        if irn:
            irn_map[s["nces_id"]] = str(irn).zfill(6)
            log.info("OH IRN for %s: %s", s["school_name"], irn_map[s["nces_id"]])
        else:
            log.warning("Could not get Ohio IRN for %s", s["school_name"])

    # Attempt to download Achievement data
    # Ohio RC download page often requires specific navigation — log as manual
    # Try a few known URL patterns first
    achievement_data = None
    for url_suffix in [
        "https://reportcard.education.ohio.gov/api/Download/DownloadFile?fileName=Achievement_2223.zip",
        "https://reportcard.education.ohio.gov/api/Download/DownloadFile?fileName=Achievement_2223.csv",
    ]:
        achievement_data = try_fetch_csv_zip(url_suffix, "achievement")
        if achievement_data:
            log.info("OH: Downloaded achievement data (%d rows)", len(achievement_data))
            break

    # Whether or not bulk download succeeded, process each school
    for school in oh_schools:
        nces_id = school["nces_id"]
        name = school["school_name"]
        irn = irn_map.get(nces_id)
        flags = []

        ela_pct = None
        math_pct = None

        if achievement_data and irn:
            # Try to find this school in the downloaded data
            school_rows = [
                r for r in achievement_data
                if str(r.get("IRN", r.get("Building IRN", ""))).zfill(6) == irn
            ]
            if school_rows:
                for row in school_rows:
                    subject = (row.get("Subject", "") or "").lower()
                    pct_raw = row.get("Pct Proficient", row.get("Percent Proficient", ""))
                    try:
                        pct = float(str(pct_raw).replace("%", "").strip())
                        if "ela" in subject or "reading" in subject or "english" in subject:
                            ela_pct = pct
                        elif "math" in subject:
                            math_pct = pct
                    except (ValueError, TypeError):
                        pass

        record = {
            "assessment": {
                "year": YEAR,
                "source": "Ohio AIR / Ohio Report Card",
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
                "source": "Ohio Value-Added System",
                "metric_name": "Value-Added Index (VAI)",
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
            flags.append("Ohio Report Card bulk data could not be fetched automatically")
            manual_url = "https://reportcard.education.ohio.gov/download"
            update_manifest_school(nces_id, name, OH_STATE, "state_assessment",
                                   status="needs_manual_download", year=YEAR,
                                   manual_url=manual_url, flags=flags)
            update_manifest_school(nces_id, name, OH_STATE, "state_growth",
                                   status="needs_manual_download", year=YEAR,
                                   manual_url=manual_url)
            update_manifest_school(nces_id, name, OH_STATE, "state_accountability",
                                   status="needs_manual_download", year=YEAR,
                                   manual_url=manual_url)
        else:
            update_manifest_school(nces_id, name, OH_STATE, "state_assessment",
                                   status="ok", year=YEAR)

        save_school(nces_id, record)
        updated += 1

    return updated, 0, failed


def main():
    from utils import load_master
    schools = load_master()
    updated, skipped, failed = process_oh_schools(schools)
    print_summary("03_fetch_oh", updated, skipped, failed)


if __name__ == "__main__":
    main()
