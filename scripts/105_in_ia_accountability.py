"""
Script 105: IN + IA accountability ratings.

Indiana: parses in_federal_accountability_2023-24.xlsx "Overall Ratings" sheet.
Iowa: manually captures Performance Profile ratings from the IA School
Performance Profile website (only HSA Des Moines is in the current data;
Davenport returns "No school or district data found").
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"


def safe_float(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s in {"*","N/A","NA","NC","NULL","<10","."}: return None
    try: return float(s)
    except: return None


def load(nid): return json.loads((BY_SCHOOL/f"{nid}.json").read_text())
def save(nid, rec):
    rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL/f"{nid}.json").write_text(json.dumps(rec, indent=2))


# Indiana — parse Overall Ratings CSV
IN_TARGETS = {
    "180006702416": "IN Math & Science Academy",
    "180009402487": "IN Math & Science Academy - North",
}


def populate_in():
    print("\n=== INDIANA accountability ===")
    path = RAW / "IN" / "in_federal_accountability_2023-24.csv"
    if not path.exists():
        print("  File missing"); return
    by_name = {}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            by_name[r.get("School Name", "").strip()] = r
    for nid, name in IN_TARGETS.items():
        r = by_name.get(name)
        if not r:
            print(f"  {nid}: '{name}' not found"); continue
        rating = (r.get("Overall Rating") or "").strip()
        rec = load(nid)
        rec["accountability"]["year"] = YEAR
        rec["accountability"]["state_rating"] = rating
        save(nid, rec)
        print(f"  {nid} {name[:50]:50}  Rating: {rating}")


# Iowa — manual capture
IA_RATINGS = {
    "199902002316": {
        "name": "Horizon Science Academy Des Moines",
        "rating": "Priority",       # Lowest tier
        "score": 38.17,             # Overall % out of 100
        "essa": "No Support Required",
    },
    # 199903302345 HSA Davenport — "No school or district data found"
}


def populate_ia():
    print("\n=== IOWA accountability ===")
    for nid, data in IA_RATINGS.items():
        rec = load(nid)
        rec["accountability"]["year"] = "2024-25"   # Iowa labels by reporting year; this is the latest published
        rec["accountability"]["state_rating"] = data["rating"]
        rec["accountability"]["state_percentile_rank"] = data["score"]
        save(nid, rec)
        print(f"  {nid} {data['name']:45}  Rating: {data['rating']}  Score: {data['score']}%")


def main():
    populate_in()
    populate_ia()
    print("\nDone. Re-run scripts/10_aggregate.py.")


if __name__ == "__main__":
    main()
