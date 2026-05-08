"""
Script 09: Fetch Indiana DOE data — ILEARN proficiency, growth, A-F accountability.

Primary source:
  - IDOE accountability: https://www.doe.in.gov/accountability/find-school-and-corporation-data-reports
  - ILEARN data downloads

Indiana schools: Indiana Math and Science Academy West, North, Central (all Indianapolis).
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

IN_STATE = "IN"
YEAR = "2022-23"

IN_ILEARN_URL = "https://www.doe.in.gov/sites/default/files/accountability/2023-ilearn-school-data.csv"
IN_MANUAL_URL = "https://www.doe.in.gov/accountability/find-school-and-corporation-data-reports"


def try_fetch_in_ilearn() -> list[dict] | None:
    urls = [
        IN_ILEARN_URL,
        "https://www.doe.in.gov/sites/default/files/assessment/2022-23-ilearn-school-level.csv",
    ]
    for url in urls:
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "csv" in ct or url.endswith(".csv"):
                text = r.content.decode("utf-8-sig", errors="replace")
                rows = list(csv.DictReader(io.StringIO(text)))
                if rows:
                    log.info("IN: Downloaded ILEARN data (%d rows)", len(rows))
                    return rows
        except Exception as exc:
            log.warning("IN: URL %s failed: %s", url, exc)
    return None


def match_in_school(rows: list[dict], name: str) -> list[dict]:
    name_lower = name.lower()
    matches = []
    for r in rows:
        sname = (r.get("School Name") or r.get("SCHOOL_NAME") or "").lower()
        if "indiana math and science" in name_lower and "indiana math" in sname:
            if "west" in name_lower and "west" in sname:
                matches.append(r)
            elif "north" in name_lower and "north" in sname:
                matches.append(r)
            elif "central" in name_lower and "central" in sname:
                matches.append(r)
    return matches


def process_in_schools(schools: list) -> tuple[int, int, int]:
    in_schools = [s for s in schools if s.get("state") == IN_STATE and s.get("nces_id")]
    updated = failed = 0

    in_data = try_fetch_in_ilearn()

    for school in in_schools:
        nces_id = school["nces_id"]
        name = school["school_name"]
        flags = []
        log.info("Processing IN: %s", name)

        ela_pct = None
        math_pct = None

        if in_data:
            school_rows = match_in_school(in_data, name)
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
                    except (ValueError, TypeError):
                        pass

        record = {
            "assessment": {
                "year": YEAR,
                "source": "Indiana ILEARN",
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
                "source": "Indiana DOE",
                "metric_name": "Indiana School Growth Metric (ILEARN)",
                "ela_growth": None,
                "math_growth": None,
                "overall_growth_rating": None,
            },
            "accountability": {
                "year": YEAR,
                "state_rating": None,  # A-F letter grade
                "state_percentile_rank": None,
                "similar_schools_percentile": None,
            },
        }

        status = "ok" if (ela_pct is not None or math_pct is not None) else "needs_manual_download"
        if status == "needs_manual_download":
            flags.append("Indiana ILEARN data requires manual download from IDOE portal")

        update_manifest_school(nces_id, name, IN_STATE, "state_assessment",
                               status=status, year=YEAR,
                               manual_url=IN_MANUAL_URL if status != "ok" else None,
                               flags=flags if flags else None)
        update_manifest_school(nces_id, name, IN_STATE, "state_growth",
                               status="needs_manual_download", year=YEAR,
                               manual_url=IN_MANUAL_URL)
        update_manifest_school(nces_id, name, IN_STATE, "state_accountability",
                               status="needs_manual_download", year=YEAR,
                               manual_url=IN_MANUAL_URL)

        save_school(nces_id, record)
        updated += 1

    return updated, 0, failed


def main():
    from utils import load_master
    schools = load_master()
    updated, skipped, failed = process_in_schools(schools)
    print_summary("09_fetch_in", updated, skipped, failed)


if __name__ == "__main__":
    main()
