"""
Script 108: Populate MO teacher data from mo_building_certification.csv.

Fields populated for each Gateway school:
- staff.teacher_fte: TEACHER_FTE
- staff.pct_teachers_certified: EDUCATOR_REG_CERT_PCT + EDUCATOR_SPEC_CERT_PCT
  (regular certification + special certification)

MO doesn't expose novice% or retention rate in this file.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"

MO_TARGETS = {
    "290059203174": "GATEWAY SCIENCE ACAD/ST LOUIS",
    "290059203205": "GATEWAY SCIENCE ACADEMY HIGH",
    "290059203244": "GATEWAY SCIENCE ACADEMY MIDDLE",
    "290059203241": "GATEWAY SCIENCE ACAD-SOUTH ELE",
}


def safe_float(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s in {"*","N/A","NA","NULL","<10","."}: return None
    try: return float(s)
    except: return None


def main() -> None:
    print("=== MO certification ===")
    path = RAW / "MO" / "mo_building_certification.csv"
    if not path.exists():
        print("  File missing"); return
    rows_by_name = {}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            if r.get("YEAR") != "2024": continue
            rows_by_name[r.get("SCHOOL_NAME", "").strip()] = r

    for nid, name in MO_TARGETS.items():
        r = rows_by_name.get(name)
        if not r:
            print(f"  {nid} '{name}': not found"); continue
        rec = json.loads((BY_SCHOOL / f"{nid}.json").read_text())
        rec["staff"]["year"] = YEAR
        fte = safe_float(r.get("TEACHER_FTE"))
        reg_pct = safe_float(r.get("EDUCATOR_REG_CERT_PCT")) or 0
        spec_pct = safe_float(r.get("EDUCATOR_SPEC_CERT_PCT")) or 0
        if fte is not None: rec["staff"]["teacher_fte"] = fte
        rec["staff"]["pct_teachers_certified"] = round(reg_pct + spec_pct, 1)
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        (BY_SCHOOL / f"{nid}.json").write_text(json.dumps(rec, indent=2))
        print(f"  {nid} {name[:50]:50}  FTE={fte}  Cert%={rec['staff']['pct_teachers_certified']}")


if __name__ == "__main__":
    main()
