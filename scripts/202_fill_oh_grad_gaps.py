"""
Script 202: Fill OH grad-rate coverage gaps surfaced by audit (Toledo + Lorain).

Audit found Graduation_Component.csv has grad data for Toledo and Lorain
that wasn't loaded into JSON. Add them.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"

# NCES → IRN for OH HSs / schools that report grad rates
OH_GRAD_FILLS = {
    "390051005220": "000338",  # Toledo
    "390136505544": "011533",  # Lorain
}


def sf(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s.upper() in {"*","N/A","NA","NULL","<10",".","-","NC"}: return None
    try: return float(s)
    except: return None


def main():
    print("=== Fill OH grad gaps (Toledo, Lorain) ===")
    fp = RAW / "OH" / "_csv_grad" / "Graduation_Component.csv"
    if not fp.exists():
        print("Graduation_Component.csv not found"); return
    by_irn = {}
    with fp.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            by_irn[(r.get("Building IRN") or "").strip()] = r

    for nid, irn in OH_GRAD_FILLS.items():
        path = BY_SCHOOL / f"{nid}.json"
        if not path.exists(): continue
        rec = json.loads(path.read_text())
        nm = rec["meta"]["school_name"]
        r = by_irn.get(irn)
        if not r: continue
        g4 = sf(r.get("Four Year Graduation Rate - Class of 2023"))
        g5 = sf(r.get("Five Year Graduation Rate - Class of 2022"))
        rec.setdefault("graduation", {})
        rec["graduation"]["year"] = "2023-24"
        if g4 is not None: rec["graduation"]["four_year_grad_rate"] = g4
        if g5 is not None: rec["graduation"]["five_year_grad_rate"] = g5
        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(rec, indent=2))
        print(f"  {nid} {nm[:40]:40}  4yr={g4}  5yr={g5}")


if __name__ == "__main__":
    main()
