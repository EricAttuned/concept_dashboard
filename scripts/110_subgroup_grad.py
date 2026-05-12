"""
Script 110: Populate graduation.by_subgroup.* for high schools.

Sources:
- IL General sheet: per-school grad rate by demographic subgroup
- OH: only has overall grad rate per IRN, not subgroups — would need a
  separate disaggregated file from the OH portal (not on disk yet).
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
    if not s or s in {"*","N/A","NA","NULL","<10","."}: return None
    try: return float(s)
    except: return None


def load(nid): return json.loads((BY_SCHOOL / f"{nid}.json").read_text())
def save(nid, rec):
    rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL / f"{nid}.json").write_text(json.dumps(rec, indent=2))


IL_TARGETS = {
    "170993005092": "Chicago Math & Sci Elem Charter",
    "170141206309": "Horizon Science Acad-Belmont Charter Sch",
    "170141006254": "Horizon Science Acad-McKinley Park Charter Sch",
    "170993006331": "Horizon Sci Academy - Southwest Charter",
}

IL_SUBGROUP_COLS = {
    "black": "High School 4-Year Graduation Rate - Black or African American",
    "hispanic": "High School 4-Year Graduation Rate - Hispanic or Latino",
    "white": "High School 4-Year Graduation Rate - White",
    "ell": "High School 4-Year Graduation Rate - EL",
    "sped": "High School 4-Year Graduation Rate - IEP",
    "frl": "High School 4-Year Graduation Rate - Low Income",
}


def populate_il_grad_subgroups():
    print("=== IL subgroup grad rates ===")
    path = RAW / "IL" / "il_assessment_general_2023-24.csv"
    if not path.exists():
        return
    rows_by_name = {}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for r in csv.DictReader(f):
            rows_by_name[r.get("School Name","").strip()] = r
    for nid, name in IL_TARGETS.items():
        r = rows_by_name.get(name)
        if not r: continue
        rec = load(nid)
        total = safe_float(r.get("High School 4-Year Graduation Rate - Total"))
        if total is None:
            # Not a high school
            continue
        rec["graduation"]["year"] = YEAR
        for sub_key, col in IL_SUBGROUP_COLS.items():
            v = safe_float(r.get(col))
            if v is not None:
                rec["graduation"]["by_subgroup"][sub_key] = v
        save(nid, rec)
        pops = {k: rec["graduation"]["by_subgroup"].get(k) for k in IL_SUBGROUP_COLS}
        print(f"  {nid} {name[:42]:42}  Black={pops['black']}  Hisp={pops['hispanic']}  White={pops['white']}  ELL={pops['ell']}  SpEd={pops['sped']}  FRL={pops['frl']}")


# OH disaggregated files — each has "Four Year Graduation Rate 2023" column
# (means Class of 2023 = 2022-23 school year grads = reported in 2023-24 card)
OH_NCES_TO_IRN_HS = {
    "390004002939": "133629",   # Cleveland HS
    "390004202978": "133660",   # Columbus HS Morse Road
    "390136605556": "011534",   # Dayton HS
}


def populate_oh_grad_subgroups():
    print("\n=== OH subgroup grad rates ===")
    OH_CSV = RAW / "OH" / "_csv"
    # (file, target group label in CSV, JSON subgroup key)
    sources = [
        ("oh_ethnic_2023-24.csv", "BLACK, NON-HISPANIC", "black"),
        ("oh_ethnic_2023-24.csv", "HISPANIC", "hispanic"),
        ("oh_ethnic_2023-24.csv", "WHITE, NON-HISPANIC", "white"),
        ("oh_econ_2023-24.csv", "ECONDISADV", "frl"),
        ("oh_ell_2023-24.csv", "ENGLEARN", "ell"),
        ("oh_sped_2023-24.csv", "DISABLED", "sped"),
    ]

    for nces_id, irn in OH_NCES_TO_IRN_HS.items():
        rec = load(nces_id)
        for fname, group_label, sub_key in sources:
            p = OH_CSV / fname
            if not p.exists(): continue
            with p.open(encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    if (r.get("Building IRN") or "").strip() != irn: continue
                    grp = (r.get("Student Group") or "").strip().strip('"').upper()
                    if grp != group_label.upper(): continue
                    v = safe_float(r.get("Four Year Graduation Rate 2023"))
                    if v is not None:
                        rec["graduation"]["by_subgroup"][sub_key] = v
                    break
        save(nces_id, rec)
        subs = rec["graduation"]["by_subgroup"]
        print(f"  {nces_id} {rec['meta']['school_name'][:42]:42}  Black={subs['black']}  Hisp={subs['hispanic']}  White={subs['white']}  ELL={subs['ell']}  SpEd={subs['sped']}  FRL={subs['frl']}")


def main():
    populate_il_grad_subgroups()
    populate_oh_grad_subgroups()


if __name__ == "__main__":
    main()
