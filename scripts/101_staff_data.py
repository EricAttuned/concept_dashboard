"""
Script 101: Populate staff/teacher fields.

Sources:
- NCES CCD directory via Urban Institute API: teachers_fte for ALL 33 schools
  (one row per (school, year). Use 2023 if available, else fall back to most recent.)
- IL General sheet: Teacher FTE, % Novice, Teacher Retention Rate (overrides NCES for IL)
- OH BUILDING_ETHNIC files: don't have staff data here, but ODE staff is in BUILDING_DISABLED
  + Achievement files don't either — for OH cert% / novice% we'd need a separate Teacher
  data file we haven't downloaded.

Idempotent.
"""
from __future__ import annotations
import csv, json, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"


def safe_float(v) -> Optional[float]:
    if v is None: return None
    s = str(v).strip().replace("%","").replace('"','').replace(",","")
    if not s or s in {"*","***","N/A","NA","NULL","<10",".","PNTS","**","-","NC","PS"}: return None
    try: return float(s)
    except: return None


def load(nid): return json.loads((BY_SCHOOL/f"{nid}.json").read_text())
def save(nid, rec):
    rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL/f"{nid}.json").write_text(json.dumps(rec, indent=2))


def fetch_nces_fte(nces_id: str, year: int = 2023) -> Optional[float]:
    """Try requested year first, then walk back if not available."""
    for try_year in (year, year-1, year-2):
        url = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{try_year}/?ncessch={nces_id}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
                if data.get("results"):
                    fte = data["results"][0].get("teachers_fte")
                    if fte and fte > 0:
                        return float(fte), try_year
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            continue
    return None, None


def populate_nces_fte() -> None:
    print("\n=== NCES CCD teachers_fte for all 33 schools ===")
    for p in sorted(BY_SCHOOL.glob("*.json")):
        rec = json.loads(p.read_text())
        nces_id = rec["meta"]["nces_id"]
        if not nces_id:
            continue
        fte, year = fetch_nces_fte(nces_id, 2023)
        if fte is None:
            print(f"  {nces_id} {rec['meta']['school_name'][:40]:40}  NO CCD data")
            continue
        rec["staff"]["teacher_fte"] = fte
        rec["staff"]["year"] = f"{year-1}-{str(year)[-2:]}"
        save(nces_id, rec)
        print(f"  {nces_id} {rec['meta']['school_name'][:40]:40}  FTE={fte}  ({year})")


def populate_il_staff() -> None:
    """Pull % Novice + Retention + better FTE from IL General sheet."""
    print("\n=== IL staff from General sheet ===")
    path = RAW / "IL" / "il_assessment_general_2023-24.csv"
    if not path.exists():
        return
    targets = {
        "170993005092": "Chicago Math & Sci Elem Charter",
        "170141206309": "Horizon Science Acad-Belmont Charter Sch",
        "170141006254": "Horizon Science Acad-McKinley Park Charter Sch",
        "170993006331": "Horizon Sci Academy - Southwest Charter",
    }
    rows = {}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            rows[r.get("School Name","").strip()] = r
    for nid, name in targets.items():
        r = rows.get(name)
        if not r: continue
        rec = load(nid)
        rec["staff"]["year"] = "2023-24"
        fte = safe_float(r.get("Total Teacher FTE"))
        novice = safe_float(r.get("% Novice Teachers"))
        retention = safe_float(r.get("Teacher Retention Rate"))
        prov = safe_float(r.get("% Teachers with Short-Term or Provisional License"))
        # % Certified = 100 - % short-term/provisional (rough proxy)
        cert = (100 - prov) if prov is not None else None

        if fte is not None: rec["staff"]["teacher_fte"] = fte
        if novice is not None: rec["staff"]["pct_teachers_novice"] = novice
        if retention is not None: rec["staff"]["teacher_retention_rate"] = retention
        if cert is not None: rec["staff"]["pct_teachers_certified"] = cert
        save(nid, rec)
        print(f"  {nid} {name[:45]:45}  FTE={fte}  Novice%={novice}  Retention%={retention}  Cert%={cert}")


def main() -> None:
    populate_nces_fte()
    populate_il_staff()
    print("\nDone. Re-run scripts/10_aggregate.py.")


if __name__ == "__main__":
    main()
