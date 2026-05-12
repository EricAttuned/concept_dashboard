"""
Script 111: Sprint 1 subgroup expansion.

Adds subgroup proficiency (race + ELL + SpEd + FRL) for MI, MO, MN, IN
where the source files already on disk have demographic breakouts.
Also extends MN graduation subgroups.

OH + IL already had subgroup proficiency populated in earlier scripts.
IA's ISASP files don't expose subgroups for HSA Des Moines (small school
all subgroups suppressed).
"""
from __future__ import annotations
import csv, json, re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"
YEAR = "2023-24"


def safe_float(v) -> Optional[float]:
    if v is None: return None
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s in {"*","***","N/A","NA","NULL","<10","."}: return None
    try: return float(s)
    except: return None


def load(nid): return json.loads((BY_SCHOOL/f"{nid}.json").read_text())
def save(nid, rec):
    rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL/f"{nid}.json").write_text(json.dumps(rec, indent=2))


# ============= INDIANA =============

IN_TARGETS = {
    "180006702416": "IN Math & Science Academy",
    "180009402487": "IN Math & Science Academy - North",
}


def in_subgroup_pct(path: Path, school_name: str, subgroup_col_idx: int) -> Optional[float]:
    """Pull School Total proficient % at subgroup_col_idx for the matching school."""
    if not path.exists(): return None
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    hdr_idx = next((i for i, r in enumerate(rows) if any("Corp ID" in (c or "") for c in r)), None)
    if hdr_idx is None: return None
    for r in rows[hdr_idx+1:]:
        if len(r) <= subgroup_col_idx: continue
        if (r[3] or "").strip() == school_name:
            v = safe_float(r[subgroup_col_idx])
            if v is None: return None
            return round(v * 100 if v <= 1.0 else v, 1)
    return None


def populate_in_subgroups():
    print("\n=== IN subgroup proficiency ===")
    # In ethnicity file: 7 groups × 7 cols each, Proficient % at offset +6
    # Groups: AmInd(10), Asian(17), Black(24), Hispanic(31), Multi(38), PI(45), White(52)
    # School Total is in the main file at col 52 already (different file)
    ETHNICITY_OFFSETS = {
        "black": 52,         # Black Proficient %  (cols 18-52: 7 groups × 5 measure cells but layout actually 7 cells × 7 groups starting at 4)
        "hispanic": 56,
        "white": 59,
        "asian": 53,         # may need adjustment
        "american_indian": 50,
        "pacific_islander": 58,
        "two_or_more": 57,
    }
    # Actually we need to figure out exact column indices. The structure: each
    # group has 7 cells (cols 4 through 52 for ELA), with Proficient % being the
    # 7th cell. So:
    # AmInd: cols 4-10, prof% at 10
    # Asian: 11-17, prof% at 17
    # Black: 18-24, prof% at 24
    # Hispanic: 25-31, prof% at 31
    # Multi: 32-38, prof% at 38
    # PI: 39-45, prof% at 45
    # White: 46-52, prof% at 52
    ETH_OFFSETS = {
        "american_indian": 10, "asian": 17, "black": 24, "hispanic": 31,
        "two_or_more": 38, "pacific_islander": 45, "white": 52,
    }
    # FRL/SpEd/ELL files use similar 7-col group layout. The relevant group is
    # typically in column position depending on layout. Looking at IN FRL file
    # header: groups are "Eligible" and "Not Eligible" — Eligible Proficient %
    # would be at col 10, Not Eligible at col 17. We want Eligible for FRL/Sped/ELL.
    DEMO_PROF_COL = 10  # "Eligible" / target group is first group in each demo file

    for nid, name in IN_TARGETS.items():
        rec = load(nid)
        for sub_key, col in ETH_OFFSETS.items():
            for subject, fname in (("ela","in_ilearn_ela_ethnicity_2023-24.csv"), ("math","in_ilearn_math_ethnicity_2023-24.csv")):
                pct = in_subgroup_pct(RAW/"IN"/fname, name, col)
                if pct is not None:
                    rec["assessment"][subject]["by_subgroup"][sub_key] = pct
        for sub_key, fname_stub in (("frl","frl"), ("sped","sped"), ("ell","ell")):
            for subject in ("ela","math"):
                pct = in_subgroup_pct(RAW/"IN"/f"in_ilearn_{subject}_{fname_stub}_2023-24.csv", name, DEMO_PROF_COL)
                if pct is not None:
                    rec["assessment"][subject]["by_subgroup"][sub_key] = pct
        save(nid, rec)
        ela_subs = rec["assessment"]["ela"]["by_subgroup"]
        math_subs = rec["assessment"]["math"]["by_subgroup"]
        print(f"  {nid} {name[:40]:40}  ELA Black={ela_subs.get('black')}  Hisp={ela_subs.get('hispanic')}  FRL={ela_subs.get('frl')}")


# ============= MN GRADUATION SUBGROUPS =============

def populate_mn_grad_subgroups():
    print("\n=== MN subgroup graduation rates ===")
    path = RAW / "MN" / "mn_mca_graduation_indicators_2023-24.csv"
    if not path.exists(): return
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    hdr_idx = next((i for i, r in enumerate(rows) if any('District\nName' in (c or '') for c in r)), None)
    if hdr_idx is None: return
    SCHOOL_COL, GROUP_COL, END_COL, FOUR_COL = 7, 12, 13, 16

    # MMSA Saint Paul = MMSA Secondary School (only HS)
    nid = "270039905179"
    rec = load(nid)
    for r in rows[hdr_idx+1:]:
        if len(r) <= FOUR_COL: continue
        school = (r[SCHOOL_COL] or "").strip()
        if school != "MMSA Secondary School": continue
        end = (r[END_COL] or "").strip()
        if end != "Graduate": continue
        group = (r[GROUP_COL] or "").strip()
        rate = safe_float(r[FOUR_COL])
        if rate is None: continue
        sub_key = None
        if "Black or African American" in group: sub_key = "black"
        elif "Hispanic" in group: sub_key = "hispanic"
        elif group == "White Students": sub_key = "white"
        elif "English Learner" in group: sub_key = "ell"
        elif "Special Education" in group: sub_key = "sped"
        elif "Free/Reduced" in group: sub_key = "frl"
        if sub_key:
            rec["graduation"]["by_subgroup"][sub_key] = rate
    save(nid, rec)
    subs = rec["graduation"]["by_subgroup"]
    print(f"  {nid} MMSA Saint Paul  Black={subs.get('black')}  Hisp={subs.get('hispanic')}  ELL={subs.get('ell')}  SpEd={subs.get('sped')}  FRL={subs.get('frl')}")


# ============= MI SUBGROUP PROFICIENCY =============

MI_TARGETS = {
    "260096708048": "Michigan Mathematics and Science Academy Lorraine",
    "260096708813": "Michigan Mathematics and Science Academy Dequindre",
}

MI_SUBGROUP_MAP = {
    "Black or African American": "black",
    "Hispanic of Any Race": "hispanic",
    "White": "white",
    "Asian": "asian",
    "American Indian or Alaska Native": "american_indian",
    "Native Hawaiian or Other Pacific Islander": "pacific_islander",
    "Two or More Races": "two_or_more",
    "English Learners": "ell",
    "Students With Disabilities": "sped",
    "Economically Disadvantaged": "frl",
}


def populate_mi_subgroups():
    print("\n=== MI subgroup proficiency ===")
    files = [
        RAW / "MI" / "mi_mstep_grades_3-8_2023-24.csv",
        RAW / "MI" / "mi_mstep_high_school_2023-24.csv",
    ]
    for nid, name in MI_TARGETS.items():
        per_subgroup: dict[str, dict[str, list[tuple[float, float]]]] = {}
        for csv_path in files:
            if not csv_path.exists(): continue
            with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
                for row in csv.DictReader(f):
                    b = (row.get("BuildingName") or "").strip().strip('"')
                    if name not in b: continue
                    cat = (row.get("ReportCategory") or "").strip().strip('"')
                    sub_key = MI_SUBGROUP_MAP.get(cat)
                    if not sub_key: continue
                    subj_raw = (row.get("Subject") or "").strip().strip('"').lower()
                    subject = "ela" if any(t in subj_raw for t in ("english","ela","reading")) else "math" if "math" in subj_raw else None
                    if subject is None: continue
                    n = safe_float(row.get("NumberAssessed"))
                    pct_adv = safe_float(row.get("PercentAdvanced"))
                    pct_prof = safe_float(row.get("PercentProficient"))
                    if n is None or n <= 0: continue
                    aoa = (pct_adv or 0) + (pct_prof or 0) if (pct_adv is not None or pct_prof is not None) else None
                    if aoa is None: continue
                    per_subgroup.setdefault(sub_key, {"ela":[], "math":[]})[subject].append((aoa, n))
        rec = load(nid)
        for sub_key, by_subj in per_subgroup.items():
            for subject, pairs in by_subj.items():
                if pairs:
                    n_total = sum(w for _, w in pairs)
                    weighted = sum(v * w for v, w in pairs) / n_total
                    if subject in ("ela", "math"):
                        rec["assessment"][subject]["by_subgroup"][sub_key] = round(weighted, 1)
        save(nid, rec)
        print(f"  {nid} {name[:50]:50}  ELA black={rec['assessment']['ela']['by_subgroup'].get('black')}  ELA hisp={rec['assessment']['ela']['by_subgroup'].get('hispanic')}  ELA frl={rec['assessment']['ela']['by_subgroup'].get('frl')}")


# ============= MO SUBGROUP PROFICIENCY =============

MO_TARGETS = {
    "290059203174": "GATEWAY SCIENCE ACAD/ST LOUIS",
    "290059203205": "GATEWAY SCIENCE ACADEMY HIGH",
    "290059203244": "GATEWAY SCIENCE ACADEMY MIDDLE",
    "290059203241": "GATEWAY SCIENCE ACAD-SOUTH ELE",
}

MO_TYPE_MAP = {
    "Black (not Hispanic)": "black",
    "Hispanic": "hispanic",
    "White (not Hispanic)": "white",
    "Asian/Pacific Islander": "asian",
    "LEP/ELL": "ell",
    "Students with Disabilities (IEP)": "sped",
    "IEP": "sped",
    "Free/Reduced Lunch": "frl",
    "FRL Status": "frl",
}


def populate_mo_subgroups():
    print("\n=== MO subgroup proficiency ===")
    csv_path = RAW / "MO" / "mo_map_school_2023-24.csv"
    if not csv_path.exists(): return
    for nid, school_name in MO_TARGETS.items():
        per_sub: dict[str, dict[str, list[tuple[float, float]]]] = {}
        with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                if (row.get("SCHOOL_NAME") or "").strip() != school_name: continue
                cat = (row.get("CATEGORY") or "").strip()
                if cat not in ("Race/Ethnicity", "Special Programs"): continue
                t = (row.get("TYPE") or "").strip()
                sub_key = MO_TYPE_MAP.get(t)
                if not sub_key: continue
                content = (row.get("CONTENT_AREA") or "").lower()
                subject = "ela" if "language" in content else "math" if "math" in content else None
                if subject is None: continue
                n = safe_float(row.get("ACCOUNTABLE"))
                pct_prof = safe_float(row.get("PROFICIENT_PCT")) or 0
                pct_adv = safe_float(row.get("ADVANCED_PCT")) or 0
                if n is None or n <= 0: continue
                aoa = pct_prof + pct_adv
                per_sub.setdefault(sub_key, {"ela":[], "math":[]})[subject].append((aoa, n))
        rec = load(nid)
        for sub_key, by_subj in per_sub.items():
            for subject, pairs in by_subj.items():
                if pairs:
                    total = sum(w for _, w in pairs)
                    rec["assessment"][subject]["by_subgroup"][sub_key] = round(sum(v*w for v,w in pairs)/total, 1)
        save(nid, rec)
        print(f"  {nid} {school_name[:50]:50}  ELA black={rec['assessment']['ela']['by_subgroup'].get('black')}  ELA hisp={rec['assessment']['ela']['by_subgroup'].get('hispanic')}  ELA frl={rec['assessment']['ela']['by_subgroup'].get('frl')}")


# ============= MN SUBGROUP PROFICIENCY =============

MN_TARGETS = {
    "270039905179": ["MMSA Elementary School", "MMSA Secondary School"],
    "270045005159": ["Horizon Science Academy Twin Cities"],
}

MN_GROUP_MAP = {
    "Black or African American Students": "black",
    "Hispanic Students": "hispanic",
    "Hispanic or Latino Students": "hispanic",
    "White Students": "white",
    "Asian Students": "asian",
    "English Learner Students": "ell",
    "Special Education Students": "sped",
    "Students Eligible for Free/Reduced-Price Meals": "frl",
}


def populate_mn_subgroups():
    print("\n=== MN subgroup proficiency ===")
    files = {
        "ela": RAW / "MN" / "mn_mca_reading_2023-24.csv",
        "math": RAW / "MN" / "mn_mca_math_2023-24.csv",
    }
    for nid, patterns in MN_TARGETS.items():
        per_sub: dict[str, dict[str, list[tuple[float, float]]]] = {}
        for subject, p in files.items():
            if not p.exists(): continue
            with p.open(encoding="utf-8-sig", errors="replace") as f:
                for row in csv.DictReader(f):
                    school = (row.get("School Name") or "").strip()
                    if not any(school == pp or school.startswith(pp) for pp in patterns): continue
                    grp = (row.get("Student Group") or "").strip()
                    sub_key = MN_GROUP_MAP.get(grp)
                    if not sub_key: continue
                    n = safe_float(row.get("Total Tested"))
                    pct = safe_float(row.get("Percent Proficient"))
                    if n is None or n <= 0 or pct is None: continue
                    if pct <= 1.0: pct *= 100
                    per_sub.setdefault(sub_key, {"ela":[], "math":[]})[subject].append((pct, n))
        rec = load(nid)
        for sub_key, by_subj in per_sub.items():
            for subject, pairs in by_subj.items():
                if pairs:
                    total = sum(w for _, w in pairs)
                    rec["assessment"][subject]["by_subgroup"][sub_key] = round(sum(v*w for v,w in pairs)/total, 1)
        save(nid, rec)
        ela_b = rec["assessment"]["ela"]["by_subgroup"].get("black")
        ela_h = rec["assessment"]["ela"]["by_subgroup"].get("hispanic")
        ela_f = rec["assessment"]["ela"]["by_subgroup"].get("frl")
        print(f"  {nid} {patterns[0][:50]:50}  ELA black={ela_b}  hisp={ela_h}  frl={ela_f}")


def main():
    populate_in_subgroups()
    populate_mi_subgroups()
    populate_mo_subgroups()
    populate_mn_subgroups()
    populate_mn_grad_subgroups()
    print("\nDone. Run scripts/10_aggregate.py")


if __name__ == "__main__":
    main()
