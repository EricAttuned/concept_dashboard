"""
Script 104: Mark MO Gateway schools' accountability status based on the APR
bottom-5% PDF we have on disk.

The PDF (missouri_accountability_apr_2023-24.pdf) is the official DESE list of
schools in the lowest 5% by APR Percent Score. We confirmed via pdfplumber that
NONE of the 4 Gateway Science Academy schools appear on this list (only the
similarly-named "GATEWAY ELEM." in St. Louis Public Schools shows up).

Therefore all 4 Gateway schools are "Above 5th Percentile / Not Identified."

Full APR percentage scores for each Gateway school are only available via the
MCDS "MSIP 6 APR 2024 - Building" interactive visualization, which requires
per-school manual lookup and isn't easily automatable.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

BY_SCHOOL = Path('/sessions/fervent-ecstatic-euler/mnt/Concept_dashboard/data/by_school')
YEAR = "2023-24"

MO_GATEWAY = {
    "290059203174": "Gateway Science Academy of St. Louis - Smiley",
    "290059203205": "Gateway Science Academy of St. Louis - High",
    "290059203244": "Gateway Science Academy of St. Louis - Middle",
    "290059203241": "Gateway Science Academy of St. Louis - South",
}


def main() -> None:
    print("=== MO Gateway accountability ===")
    for nces_id, name in MO_GATEWAY.items():
        rec = json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())
        rec["accountability"]["year"] = YEAR
        rec["accountability"]["state_rating"] = "Above 5th Percentile"
        # We don't have the precise APR percent for each Gateway school from this PDF —
        # only the confirmation they're NOT in the bottom 5%. Leave the percentile_rank
        # field null, but the state_rating clearly indicates the status.
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(rec, indent=2))
        print(f"  {nces_id} {name[:50]:50}  Status=Above 5th Percentile (not on DESE bottom-5% list)")


if __name__ == "__main__":
    main()
