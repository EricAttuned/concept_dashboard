"""
Script 204: Build state + host-district benchmark data for the dashboard.

Output: data/aggregated/benchmarks.json
Schema:
{
  "by_school": {
    "<nces_id>": {
       "district_name": "...",
       "district": {ela: x, math: y, attendance: z, ...},
       "state":    {ela: x, math: y, attendance: z, ...},
       "school_year": "2023-24"
    }
  },
  "by_state": {
    "OH": {ela: ..., math: ..., attendance: ..., ...},
    ...
  }
}
"""
from __future__ import annotations
import csv, json, os
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "aggregated" / "benchmarks.json"

YEAR = "2023-24"


def sf(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s.upper() in {"*","N/A","NA","NULL","<10",".","-","NC"}: return None
    try: return float(s)
    except: return None


# Each school's host-district name in the state's source file
HOST_DISTRICTS = {
    "170141006254": "Chicago Public Schools District 299",  # HSA McKinley Park
    "170141206309": "Chicago Public Schools District 299",  # HSA Belmont
    "170993005092": "Chicago Public Schools District 299",  # Chicago Math & Sci
    "170993006331": "Chicago Public Schools District 299",  # Southwest
    "180006702416": "Indianapolis Public Schools",          # IMSA West
    "180009402487": "Indianapolis Public Schools",          # IMSA North
    "199902002316": "Des Moines Independent Community School District",
    "199903302345": "Davenport Community School District",
    "260096708048": "Michigan Mathematics and Science Academy",  # Lorraine (PSA self-district)
    "260096708813": "Michigan Mathematics and Science Academy",  # Dequindre
    "270039905179": "Saint Paul Public Schools",            # MMSA
    "270045005159": "Minneapolis Public Schools",           # HSA Twin Cities
    "290059203174": "GATEWAY SCIENCE ACADEMY",              # Gateway St Louis - charter LEA
    "290059203205": "GATEWAY SCIENCE ACADEMY",
    "290059203241": "GATEWAY SCIENCE ACADEMY",
    "290059203244": "GATEWAY SCIENCE ACADEMY",
    "390004002939": "Cleveland Municipal",       # OH Cleveland HS
    "390004202978": "Columbus City",             # OH Columbus HS
    "390044105000": "Cincinnati City",
    "390044405003": "Dayton City",
    "390045105010": "Toledo City",               # OH "Springfield" is in Toledo
    "390045405013": "Cleveland Municipal",
    "390047005029": "Cleveland Municipal",
    "390051005220": "Toledo City",
    "390064505319": "Columbus City",
    "390064605345": "Cleveland Municipal",       # Noble Academy Euclid registered as Cleveland district
    "390132205440": "Columbus City",
    "390135305483": "Columbus City",
    "390136505544": "Lorain City",
    "390136605556": "Dayton City",
    "390138305625": "Dayton City",
    "390138905567": "Youngstown City",
    "390160605963": "Columbus City",
}


# ===== IL =====
def build_IL_benchmarks():
    state = {}; districts = {}
    # IAR ELA/Math
    fp = RAW / "IL" / "il_assessment_iar_2023-24.csv"
    if fp.exists():
        with fp.open(encoding="utf-8-sig", errors="replace") as f:
            for r in csv.DictReader(f):
                if r.get("Type") == "Statewide":
                    state["ela_iar"] = sf(r.get("IAR ELA Proficiency Rate - Total"))
                    state["math_iar"] = sf(r.get("IAR Math Proficiency Rate - Total"))
                elif r.get("Type") == "District":
                    dn = r.get("District", "")
                    if not dn: continue
                    districts.setdefault(dn, {})
                    districts[dn]["ela_iar"] = sf(r.get("IAR ELA Proficiency Rate - Total"))
                    districts[dn]["math_iar"] = sf(r.get("IAR Math Proficiency Rate - Total"))
    fp = RAW / "IL" / "il_assessment_sat_2023-24.csv"
    if fp.exists():
        with fp.open(encoding="utf-8-sig", errors="replace") as f:
            for r in csv.DictReader(f):
                if r.get("Type") == "Statewide":
                    state["ela_sat"] = sf(r.get("SAT ELA Proficiency Rate - Total"))
                    state["math_sat"] = sf(r.get("SAT Math Proficiency Rate - Total"))
                elif r.get("Type") == "District":
                    dn = r.get("District", "")
                    if not dn: continue
                    districts.setdefault(dn, {})
                    districts[dn]["ela_sat"] = sf(r.get("SAT ELA Proficiency Rate - Total"))
                    districts[dn]["math_sat"] = sf(r.get("SAT Math Proficiency Rate - Total"))
    fp = RAW / "IL" / "il_assessment_general_2023-24.csv"
    if fp.exists():
        with fp.open(encoding="utf-8-sig", errors="replace") as f:
            for r in csv.DictReader(f):
                t = r.get("Type")
                target = state if t == "Statewide" else None
                if t == "District":
                    dn = r.get("District", "")
                    if not dn: continue
                    target = districts.setdefault(dn, {})
                if target is None: continue
                target["attendance"] = sf(r.get("Student Attendance Rate"))
                target["chronic"] = sf(r.get("Chronic Absenteeism"))
                target["grad_4yr"] = sf(r.get("High School 4-Year Graduation Rate - Total"))
                target["grad_5yr"] = sf(r.get("High School 5-Year Graduation Rate - Total"))
                target["retention"] = sf(r.get("Teacher Retention Rate"))
    return state, districts


# ===== OH =====
def build_OH_benchmarks():
    """OH: pull state averages from the file's 'Statewide Average' columns.
    For district-level we compute weighted averages over building rows within
    each district (enrollment-weighted)."""
    state = {}; districts: dict = {}

    # State avg grad from Graduation_Component
    fp_grad = RAW / "OH" / "_csv_grad" / "Graduation_Component.csv"
    if fp_grad.exists():
        # District aggregation: collect per-building (numerator, denominator) pairs
        # and compute district-level rate. Only buildings with non-NC values count.
        dist_g4 = {}  # district -> [(num, denom), ...]
        dist_g5 = {}
        with fp_grad.open(encoding="utf-8-sig", errors="replace") as f:
            for r in csv.DictReader(f):
                # State average comes from the dedicated column on any row
                if not state.get("grad_4yr"):
                    state["grad_4yr"] = sf(r.get("Four Year Graduation Rate - Statewide Average - Class of 2023"))
                    state["grad_5yr"] = sf(r.get("Five Year Graduation Rate - Statewide Average - Class of 2022"))
                dn = (r.get("District Name") or "").strip()
                if not dn: continue
                n4 = sf(r.get("Four Year Graduation Rate Numerator - Class of 2023"))
                d4 = sf(r.get("Four Year Graduation Rate Denominator - Class of 2023"))
                n5 = sf(r.get("Five Year Graduation Rate Numerator - Class of 2022"))
                d5 = sf(r.get("Five Year Graduation Rate Denominator - Class of 2022"))
                if n4 is not None and d4 is not None and d4 > 0:
                    dist_g4.setdefault(dn, [0, 0])
                    dist_g4[dn][0] += n4
                    dist_g4[dn][1] += d4
                if n5 is not None and d5 is not None and d5 > 0:
                    dist_g5.setdefault(dn, [0, 0])
                    dist_g5[dn][0] += n5
                    dist_g5[dn][1] += d5
        for dn, (n, d) in dist_g4.items():
            districts.setdefault(dn, {})["grad_4yr"] = round(n/d*100, 1) if d else None
        for dn, (n, d) in dist_g5.items():
            districts.setdefault(dn, {})["grad_5yr"] = round(n/d*100, 1) if d else None

    return state, districts


# ===== IN, IA, MI, MO, MN =====
def build_simple_benchmarks(state_code):
    """For states where we just compute the network average as a proxy benchmark."""
    return {}, {}


def main():
    benchmarks = {"generated_at": datetime.now(timezone.utc).isoformat(),
                  "school_year": YEAR, "by_state": {}, "by_school": {}}

    il_state, il_dist = build_IL_benchmarks()
    benchmarks["by_state"]["IL"] = il_state
    oh_state, oh_dist = build_OH_benchmarks()
    benchmarks["by_state"]["OH"] = oh_state

    # For each school, pull state + relevant district
    for fn in sorted(os.listdir(BY_SCHOOL)):
        if not fn.endswith(".json"): continue
        nid = fn[:-5]
        rec = json.loads((BY_SCHOOL / fn).read_text())
        st = rec.get("meta", {}).get("state", "")
        district_name = HOST_DISTRICTS.get(nid, "")
        state_bench = benchmarks["by_state"].get(st, {})
        district_bench = {}
        if st == "IL":
            district_bench = il_dist.get(district_name, {})
        elif st == "OH":
            # OH district name in grad file may be different from achievement file
            # Try a fuzzy match
            for dn, d in oh_dist.items():
                if district_name.lower() in dn.lower():
                    district_bench = d; break
        benchmarks["by_school"][nid] = {
            "school_name": rec["meta"]["school_name"],
            "district_name": district_name,
            "state_code": st,
            "state": state_bench,
            "district": district_bench,
        }

    OUT.write_text(json.dumps(benchmarks, indent=2))
    print(f"Wrote {OUT}")
    print(f"States with benchmarks: {list(benchmarks['by_state'].keys())}")
    print(f"Schools with district benchmark: {sum(1 for s in benchmarks['by_school'].values() if s['district'])}")


if __name__ == "__main__":
    main()
