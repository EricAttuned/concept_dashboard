"""
Script 200: Full dashboard audit.

For every school + metric, re-derive the value from the raw source and compare
against the JSON value in data/by_school/<NCES_ID>.json. Outputs:
  AUDIT_RESULTS.tsv  — all checks, full detail
  AUDIT_SUMMARY.md   — top-level summary + mismatches

Status codes:
  OK              — JSON and source match within tolerance
  OK_NULL         — Both JSON and source are null (no data available, expected)
  MISMATCH        — JSON and source disagree
  MISSING_SOURCE  — JSON has value but source file/row not found
  STRUCTURAL_DIFF — Comparing aggregates that can't be perfectly compared (e.g. OH all-subjects overall vs JSON ELA-only)
"""
from __future__ import annotations
import csv, json, os
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"


def sf(v):
    s = str(v or "").strip().replace("%","").replace('"','')
    if not s or s.upper() in {"*","N/A","NA","NULL","<10",".","-","NC"}: return None
    try: return float(s)
    except: return None


def approx_eq(a, b, tol=0.5):
    if a is None and b is None: return True
    if a is None or b is None: return False
    return abs(a - b) <= tol


def fmt(v):
    if v is None: return "—"
    if isinstance(v, float): return f"{v:.1f}"
    return str(v)


findings = []


def record(state, nid, name, metric, json_v, source_v, status, src_file="", notes=""):
    findings.append({"state":state,"nces_id":nid,"school_name":name,"metric":metric,
                     "json_value":fmt(json_v),"source_value":fmt(source_v),
                     "status":status,"source_file":src_file,"notes":notes})


def load_rec(nid):
    p = BY_SCHOOL / f"{nid}.json"
    if not p.exists(): return None
    return json.loads(p.read_text())


# ============================================================
# IL
# ============================================================
IL_TARGETS = {
    "170993005092": "Chicago Math & Sci Elem Charter",
    "170141206309": "Horizon Science Acad-Belmont Charter Sch",
    "170141006254": "Horizon Science Acad-McKinley Park Charter Sch",
    "170993006331": "Horizon Sci Academy - Southwest Charter",
}
IL_GRAD_SUBS = {
    "black":"High School 4-Year Graduation Rate - Black or African American",
    "hispanic":"High School 4-Year Graduation Rate - Hispanic or Latino",
    "white":"High School 4-Year Graduation Rate - White",
    "ell":"High School 4-Year Graduation Rate - EL",
    "sped":"High School 4-Year Graduation Rate - IEP",
    "frl":"High School 4-Year Graduation Rate - Low Income",
}


def audit_IL():
    fp = RAW/"IL"/"il_assessment_general_2023-24.csv"
    rows = {}
    if fp.exists():
        with fp.open(encoding="utf-8-sig",errors="replace") as f:
            for r in csv.DictReader(f):
                rows[(r.get("School Name") or "").strip()] = r
    for nid, sname in IL_TARGETS.items():
        rec = load_rec(nid)
        if not rec: continue
        nm = rec["meta"]["school_name"]
        r = rows.get(sname)
        if not r:
            record("IL",nid,nm,"*",None,None,"MISSING_SOURCE",fp.name,f"name not in file"); continue
        # Attendance
        record("IL",nid,nm,"attendance.rate",
               (rec.get("attendance") or {}).get("avg_daily_attendance_rate"),
               sf(r.get("Student Attendance Rate")),
               status_for((rec.get("attendance") or {}).get("avg_daily_attendance_rate"),
                          sf(r.get("Student Attendance Rate"))), fp.name)
        record("IL",nid,nm,"attendance.chronic",
               (rec.get("attendance") or {}).get("chronic_absenteeism_rate"),
               sf(r.get("Chronic Absenteeism")),
               status_for((rec.get("attendance") or {}).get("chronic_absenteeism_rate"),
                          sf(r.get("Chronic Absenteeism"))), fp.name)
        # Grad
        record("IL",nid,nm,"graduation.4yr",
               (rec.get("graduation") or {}).get("four_year_grad_rate"),
               sf(r.get("High School 4-Year Graduation Rate - Total")),
               status_for((rec.get("graduation") or {}).get("four_year_grad_rate"),
                          sf(r.get("High School 4-Year Graduation Rate - Total"))), fp.name)
        record("IL",nid,nm,"graduation.5yr",
               (rec.get("graduation") or {}).get("five_year_grad_rate"),
               sf(r.get("High School 5-Year Graduation Rate - Total")),
               status_for((rec.get("graduation") or {}).get("five_year_grad_rate"),
                          sf(r.get("High School 5-Year Graduation Rate - Total"))), fp.name)
        # Subgroup grad
        gb = (rec.get("graduation") or {}).get("by_subgroup",{}) or {}
        for key, col in IL_GRAD_SUBS.items():
            j = gb.get(key); s = sf(r.get(col))
            record("IL",nid,nm,f"grad.sub.{key}",j,s,status_for(j,s),fp.name)
        # Teacher Retention Rate (IL publishes it)
        ret_j = (rec.get("staff") or {}).get("teacher_retention_rate")
        ret_s = sf(r.get("Teacher Retention Rate"))
        record("IL",nid,nm,"staff.retention",ret_j,ret_s,status_for(ret_j,ret_s),fp.name)
        # ELA + Math proficient (from il_assessment_ela_math_science)
    # Cross-check ELA/Math against the IAR + SAT files (IAR for K-8, SAT for HS)
    iar_fp = RAW/"IL"/"il_assessment_iar_2023-24.csv"
    sat_fp = RAW/"IL"/"il_assessment_sat_2023-24.csv"
    iar_rows = {}; sat_rows = {}
    if iar_fp.exists():
        with iar_fp.open(encoding="utf-8-sig",errors="replace") as f:
            for r in csv.DictReader(f):
                iar_rows[(r.get("School Name") or "").strip()] = r
    if sat_fp.exists():
        with sat_fp.open(encoding="utf-8-sig",errors="replace") as f:
            for r in csv.DictReader(f):
                sat_rows[(r.get("School Name") or "").strip()] = r
    for nid, sname in IL_TARGETS.items():
        rec = load_rec(nid)
        if not rec: continue
        nm = rec["meta"]["school_name"]
        ela_j = ((rec.get("assessment") or {}).get("ela") or {}).get("pct_proficient_all")
        math_j = ((rec.get("assessment") or {}).get("math") or {}).get("pct_proficient_all")
        iar = iar_rows.get(sname); sat = sat_rows.get(sname)
        ela_s = math_s = None
        if iar:
            ela_s = sf(iar.get("IAR ELA Proficiency Rate - Total"))
            math_s = sf(iar.get("IAR Math Proficiency Rate - Total"))
        if ela_s is None and sat:
            ela_s = sf(sat.get("SAT ELA Proficiency Rate - Total") or sat.get("SAT ERW Proficiency Rate - Total"))
            math_s = math_s if math_s is not None else sf(sat.get("SAT Math Proficiency Rate - Total"))
        record("IL",nid,nm,"assess.ela",ela_j,ela_s,status_for(ela_j,ela_s),iar_fp.name)
        record("IL",nid,nm,"assess.math",math_j,math_s,status_for(math_j,math_s),iar_fp.name)


# ============================================================
# MN
# ============================================================
MN_TARGETS = {
    "270045005159": ["Horizon Science Academy Twin Cities"],
    "270039905179": ["MMSA Elementary School","MMSA Secondary School"],
}


def _mn_weighted_pct(fp, names):
    if not fp.exists(): return None
    matched = []
    with fp.open(encoding="utf-8-sig",errors="replace") as f:
        for r in csv.DictReader(f):
            if (r.get("School Name") or "").strip() not in names: continue
            if (r.get("Student Group") or "").strip() != "All students": continue
            if (r.get("Grade") or "").strip() != "0": continue
            t = sf(r.get("Count Valid Scores MCA"))
            p = sf(r.get("Percent Proficient"))
            if t and p is not None: matched.append((t,p))
    if not matched: return None
    total = sum(t for t,_ in matched)
    return round(sum(t*p for t,p in matched)/total*100, 1) if total else None


def audit_MN():
    for nid, names in MN_TARGETS.items():
        rec = load_rec(nid)
        if not rec: continue
        nm = rec["meta"]["school_name"]
        ela_j = ((rec.get("assessment") or {}).get("ela") or {}).get("pct_proficient_all")
        math_j = ((rec.get("assessment") or {}).get("math") or {}).get("pct_proficient_all")
        ela_s = _mn_weighted_pct(RAW/"MN"/"mn_mca_reading_2023-24.csv", names)
        math_s = _mn_weighted_pct(RAW/"MN"/"mn_mca_math_2023-24.csv", names)
        record("MN",nid,nm,"assess.ela",ela_j,ela_s,status_for(ela_j,ela_s),
               "mn_mca_reading_2023-24.csv","Grade=0 All students")
        record("MN",nid,nm,"assess.math",math_j,math_s,status_for(math_j,math_s),
               "mn_mca_math_2023-24.csv","Grade=0 All students")
        # MMR attendance
        mmr_fp = RAW/"MN"/"mn_mca_mmr_accountability_2023-24.csv"
        if mmr_fp.exists():
            # Find Consistent Attendance for school
            with mmr_fp.open(encoding="utf-8-sig",errors="replace") as f:
                content = f.read().splitlines()
            # First find header row
            hdr_idx = None
            for i, line in enumerate(content[:30]):
                if "School Name" in line and "District" in line:
                    hdr_idx = i; break
            if hdr_idx is None: hdr_idx = 0
            rdr = csv.DictReader(content[hdr_idx:])
            for r in rdr:
                if (r.get("School Name") or "").strip() in names:
                    ca = sf(r.get("Consistent Attendance Rate") or r.get("Consistent Attendance"))
                    att_j = (rec.get("attendance") or {}).get("avg_daily_attendance_rate")
                    chr_j = (rec.get("attendance") or {}).get("chronic_absenteeism_rate")
                    if ca is not None:
                        record("MN",nid,nm,"attendance.rate",att_j,ca,status_for(att_j,ca),mmr_fp.name)
                        record("MN",nid,nm,"attendance.chronic",chr_j,round(100-ca,1),status_for(chr_j,round(100-ca,1)),mmr_fp.name)
                    break


# ============================================================
# MO
# ============================================================
MO_TARGETS = {
    "290059203174": "GATEWAY SCIENCE ACAD/ST LOUIS",
    "290059203205": "GATEWAY SCIENCE ACADEMY HIGH",
    "290059203244": "GATEWAY SCIENCE ACADEMY MIDDLE",
    "290059203241": "GATEWAY SCIENCE ACAD-SOUTH ELE",
}


def audit_MO():
    fp = RAW/"MO"/"mo_proportional_attendance.csv"
    if fp.exists():
        rows = {}
        with fp.open(encoding="utf-8-sig",errors="replace") as f:
            for r in csv.DictReader(f):
                if r.get("YEAR") != "2024": continue
                rows[(r.get("SCHOOL_NAME") or "").strip()] = r
        for nid, name in MO_TARGETS.items():
            rec = load_rec(nid)
            if not rec: continue
            nm = rec["meta"]["school_name"]
            r = rows.get(name)
            if not r: continue
            prop = sf(r.get("PROPORTIONAL_ATTENDANCE_TOTAL_PCT"))
            att_j = (rec.get("attendance") or {}).get("avg_daily_attendance_rate")
            chr_j = (rec.get("attendance") or {}).get("chronic_absenteeism_rate")
            record("MO",nid,nm,"attendance.proportional",att_j,prop,status_for(att_j,prop),fp.name)
            chr_s = round(100-prop,1) if prop is not None else None
            record("MO",nid,nm,"attendance.chronic",chr_j,chr_s,status_for(chr_j,chr_s),fp.name)


# ============================================================
# OH
# ============================================================
OH_NCES_TO_IRN = {
    "390004002939":"133629","390004202978":"133660","390044105000":"000804",
    "390044405003":"000808","390045105010":"000825","390045405013":"000838",
    "390047005029":"000858","390051005220":"000338","390064505319":"008280",
    "390064605345":"008278","390132205440":"009179","390135305483":"009990",
    "390136505544":"011533","390136605556":"011534","390138305625":"011976",
    "390138905567":"011986","390160605963":"017123",
}


def audit_OH():
    # Achievement file
    ach = {}
    fp_ach = RAW/"OH"/"_csv"/"oh_achievement_2023-24.csv"
    if fp_ach.exists():
        with fp_ach.open(encoding="utf-8-sig",errors="replace") as f:
            for r in csv.DictReader(f):
                ach[(r.get("Building IRN") or "").strip()] = r
    # Grad file
    grad = {}
    fp_grad = RAW/"OH"/"_csv_grad"/"Graduation_Component.csv"
    if fp_grad.exists():
        with fp_grad.open(encoding="utf-8-sig",errors="replace") as f:
            for r in csv.DictReader(f):
                grad[(r.get("Building IRN") or "").strip()] = r

    for nid, irn in OH_NCES_TO_IRN.items():
        rec = load_rec(nid)
        if not rec: continue
        nm = rec["meta"]["school_name"]
        # Star rating
        a_row = ach.get(irn)
        if a_row:
            sr_j = (rec.get("accountability") or {}).get("state_rating","") or ""
            sr_s = (a_row.get("Achievement Component Star Rating") or "").strip()
            if sr_j or sr_s:
                # Compare e.g. "2 Stars" matches "2 Stars"
                ok = (sr_j.split(" ")[0] == sr_s.split(" ")[0]) if (sr_j and sr_s) else (sr_j == sr_s)
                record("OH",nid,nm,"accountability.rating",sr_j,sr_s,
                       "OK" if ok else "MISMATCH",fp_ach.name)
        # Grad rates
        g_row = grad.get(irn)
        if g_row:
            g4_j = (rec.get("graduation") or {}).get("four_year_grad_rate")
            g4_s = sf(g_row.get("Four Year Graduation Rate - Class of 2023"))
            g5_j = (rec.get("graduation") or {}).get("five_year_grad_rate")
            g5_s = sf(g_row.get("Five Year Graduation Rate - Class of 2022"))
            record("OH",nid,nm,"graduation.4yr",g4_j,g4_s,status_for(g4_j,g4_s),fp_grad.name)
            record("OH",nid,nm,"graduation.5yr",g5_j,g5_s,status_for(g5_j,g5_s),fp_grad.name)


# ============================================================
# IN
# ============================================================
IN_TARGETS = {
    "180009402487": "IN Math & Science Academy - North",
    "180006702416": "IN Math & Science Academy",  # West
}


def _in_pct_total(fp, name):
    """IN file has multi-line header; School Total proficient % is at a known offset.
    Header line 3 indicates 'School Total' columns; the proficient % is the last col."""
    if not fp.exists(): return None
    with fp.open(encoding="utf-8-sig",errors="replace") as f:
        rows = list(csv.reader(f))
    # Find header row(s) — School Name is in col 3
    data_start = 0
    for i, r in enumerate(rows):
        if len(r) > 3 and r[3] == "School Name":
            data_start = i + 1; break
    for r in rows[data_start:]:
        if len(r) > 3 and r[3] == name:
            # Last column (School Total Proficient %) is the rightmost float < 1
            for cell in reversed(r):
                v = sf(cell)
                if v is not None and 0 <= v <= 1.0:
                    return round(v*100, 1)
            break
    return None


def audit_IN():
    for nid, name in IN_TARGETS.items():
        rec = load_rec(nid)
        if not rec: continue
        nm = rec["meta"]["school_name"]
        ela_j = ((rec.get("assessment") or {}).get("ela") or {}).get("pct_proficient_all")
        math_j = ((rec.get("assessment") or {}).get("math") or {}).get("pct_proficient_all")
        ela_s = _in_pct_total(RAW/"IN"/"in_ilearn_ela_2023-24.csv", name)
        math_s = _in_pct_total(RAW/"IN"/"in_ilearn_math_2023-24.csv", name)
        record("IN",nid,nm,"assess.ela",ela_j,ela_s,status_for(ela_j,ela_s),"in_ilearn_ela_2023-24.csv")
        record("IN",nid,nm,"assess.math",math_j,math_s,status_for(math_j,math_s),"in_ilearn_math_2023-24.csv")
        # Accountability
        acc_j = (rec.get("accountability") or {}).get("state_rating")
        fp = RAW/"IN"/"in_federal_accountability_2023-24.csv"
        if fp.exists():
            with fp.open(encoding="utf-8-sig",errors="replace") as f:
                for r in csv.DictReader(f):
                    if (r.get("School Name") or "").strip().lower() != name.lower(): continue
                    # Find an accountability column
                    for k in ["Federal Accountability","Designation","Federal Designation","Title I School Designation"]:
                        v = r.get(k)
                        if v:
                            record("IN",nid,nm,"accountability.rating",acc_j,v,
                                   "OK" if acc_j and v and (v.lower() in acc_j.lower() or acc_j.lower() in v.lower()) else "MISMATCH",
                                   fp.name)
                            break
                    break


# ============================================================
# IA
# ============================================================
def audit_IA():
    nid = "199902002316"
    rec = load_rec(nid)
    if not rec: return
    nm = rec["meta"]["school_name"]
    fp = RAW/"IA"/"ia_teacher_info_2023-24.csv"
    if fp.exists():
        with fp.open(encoding="utf-8-sig",errors="replace") as f:
            for row in csv.reader(f):
                if len(row) < 30: continue
                if (row[3] or "").strip().lower() == "horizon science academy":
                    ft = sf(row[6]); beg = sf(row[19])
                    nov = round(beg/ft*100,1) if (ft and beg is not None) else None
                    record("IA",nid,nm,"staff.teacher_fte",
                           (rec.get("staff") or {}).get("teacher_fte"), ft,
                           status_for((rec.get("staff") or {}).get("teacher_fte"), ft), fp.name)
                    record("IA",nid,nm,"staff.novice",
                           (rec.get("staff") or {}).get("pct_teachers_novice"), nov,
                           status_for((rec.get("staff") or {}).get("pct_teachers_novice"), nov), fp.name)
                    break


# ============================================================
# MI
# ============================================================
MI_TARGETS = {
    "260096708048": "Michigan Mathematics and Science Academy Lorraine",
    "260096708813": "Michigan Mathematics and Science Academy Dequindre",
}


def audit_MI():
    # MI M-STEP files have multi-row layout with subject, grade, subgroup
    fp_ms = RAW/"MI"/"mi_mstep_grades_3-8_2023-24.csv"
    if not fp_ms.exists():
        return
    rows_by_school = {}
    with fp_ms.open(encoding="utf-8-sig",errors="replace") as f:
        for r in csv.DictReader(f):
            nm = (r.get("BuildingName") or r.get("Building Name") or r.get("School Name") or "").strip()
            rows_by_school.setdefault(nm, []).append(r)
    for nid, sname in MI_TARGETS.items():
        rec = load_rec(nid)
        if not rec: continue
        nm = rec["meta"]["school_name"]
        rs = rows_by_school.get(sname, [])
        if not rs:
            record("MI",nid,nm,"*",None,None,"MISSING_SOURCE",fp_ms.name,
                   f"name '{sname}' not in file"); continue
        # The MI file is per-subject + grade with ReportCategory (subgroup).
        # MI defines "Proficient" = Advanced + Proficient (top two levels).
        # MI uses band-suppression for small cells ("<=10%", "<=20%", "<=30%").
        # The production parser uses midpoint of each band (e.g. <=20% → 10);
        # we replicate that here to compare apples-to-apples.
        def mi_safe(v):
            s = str(v or "").strip().replace("%","").replace('"','')
            if not s or s.upper() in {"*","N/A","NA","NULL","<10",".","-"}: return None
            if s.startswith("<="):
                try: return float(s[2:]) / 2
                except: return None
            if s.startswith(">="):
                try: t = float(s[2:]); return (t + 100) / 2
                except: return None
            try: return float(s)
            except: return None

        # Production parser only counts rows where (a) NumberAssessed parses
        # to a positive number (rejecting "<10") and (b) at least PercentProficient
        # is non-null. Replicate that exactly so we audit apples-to-apples.
        def agg(subject_kws):
            pairs = []
            for r in rs:
                subj = (r.get("Subject") or "").strip().lower()
                if not any(kw in subj for kw in subject_kws): continue
                grp = (r.get("ReportCategory") or "").strip()
                if grp != "All Students": continue
                n = mi_safe(r.get("NumberAssessed"))
                if n is None or n <= 0: continue
                pa = mi_safe(r.get("PercentAdvanced"))
                pp = mi_safe(r.get("PercentProficient"))
                if pa is not None and pp is not None:
                    pct = pa + pp
                elif pp is not None:
                    pct = pp
                else:
                    continue
                pairs.append((pct, n))
            if not pairs: return None
            wt = sum(n for _, n in pairs)
            return round(sum(p*n for p,n in pairs) / wt, 1) if wt else None
        ela_s = agg(["ela","english","reading"])
        math_s = agg(["math"])
        ela_j = ((rec.get("assessment") or {}).get("ela") or {}).get("pct_proficient_all")
        math_j = ((rec.get("assessment") or {}).get("math") or {}).get("pct_proficient_all")
        record("MI",nid,nm,"assess.ela",ela_j,ela_s,status_for(ela_j,ela_s),fp_ms.name,"Weighted across grades")
        record("MI",nid,nm,"assess.math",math_j,math_s,status_for(math_j,math_s),fp_ms.name,"Weighted across grades")


def status_for(j, s):
    if j is None and s is None: return "OK_NULL"
    if j is None or s is None: return "MISSING_SOURCE"
    return "OK" if approx_eq(j, s) else "MISMATCH"


# ============================================================
# Audit teacher FTE coverage (cross-state)
# ============================================================
def audit_teacher_coverage():
    """Check that every school with a state has SOME teacher data, or flag null."""
    for fn in sorted(os.listdir(BY_SCHOOL)):
        if not fn.endswith(".json"): continue
        rec = json.loads((BY_SCHOOL/fn).read_text())
        nm = rec["meta"]["school_name"]
        st = rec["meta"].get("state")
        s = rec.get("staff", {}) or {}
        fte = s.get("teacher_fte")
        if fte is None:
            record(st or "?", fn[:-5], nm, "staff.teacher_fte", None, None, "MISSING_SOURCE", "", "no FTE populated")


def audit_completeness():
    """Tally completeness of every metric across the network."""
    metrics_to_check = {
        "enrollment.total": lambda r: (r.get("enrollment") or {}).get("total"),
        "assess.ela": lambda r: ((r.get("assessment") or {}).get("ela") or {}).get("pct_proficient_all"),
        "assess.math": lambda r: ((r.get("assessment") or {}).get("math") or {}).get("pct_proficient_all"),
        "attendance.rate": lambda r: (r.get("attendance") or {}).get("avg_daily_attendance_rate"),
        "attendance.chronic": lambda r: (r.get("attendance") or {}).get("chronic_absenteeism_rate"),
        "graduation.4yr": lambda r: (r.get("graduation") or {}).get("four_year_grad_rate"),
        "staff.teacher_fte": lambda r: (r.get("staff") or {}).get("teacher_fte"),
        "staff.cert": lambda r: (r.get("staff") or {}).get("pct_teachers_certified"),
        "staff.novice": lambda r: (r.get("staff") or {}).get("pct_teachers_novice"),
        "staff.retention": lambda r: (r.get("staff") or {}).get("teacher_retention_rate"),
        "accountability.rating": lambda r: (r.get("accountability") or {}).get("state_rating"),
        "trend.prior_year_ela": lambda r: ((r.get("trends") or {}).get("ela_proficiency_by_year") or {}).get("2022-23"),
    }
    cov = {k: 0 for k in metrics_to_check}
    total = 0
    for fn in sorted(os.listdir(BY_SCHOOL)):
        if not fn.endswith(".json"): continue
        rec = json.loads((BY_SCHOOL/fn).read_text())
        total += 1
        for k, fn_ in metrics_to_check.items():
            v = fn_(rec)
            if v is not None: cov[k] += 1
    return total, cov


def main():
    audit_IL()
    audit_MN()
    audit_MO()
    audit_OH()
    audit_IN()
    audit_IA()
    audit_MI()

    out = ROOT/"AUDIT_RESULTS.tsv"
    cols = ["state","nces_id","school_name","metric","json_value","source_value","status","source_file","notes"]
    with out.open("w") as f:
        f.write("\t".join(cols) + "\n")
        for r in findings:
            f.write("\t".join(str(r.get(c,"")) for c in cols) + "\n")
    print(f"Wrote {out}")

    c = Counter(r["status"] for r in findings)
    print(f"\nTotal cross-source checks: {len(findings)}")
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        pct = round(100*v/len(findings),1) if findings else 0
        print(f"  {k:20} {v:4}  ({pct}%)")

    # Print mismatches
    mismatches = [r for r in findings if r["status"] == "MISMATCH"]
    if mismatches:
        print(f"\n=== MISMATCHES ({len(mismatches)}) ===")
        for r in mismatches:
            print(f"  [{r['state']}] {r['school_name'][:35]:35} | {r['metric']:30} | JSON={r['json_value']} | Source={r['source_value']} | {r['notes']}")

    # Completeness sub-report
    total, cov = audit_completeness()
    print(f"\n=== COMPLETENESS ({total} schools) ===")
    for k, v in cov.items():
        print(f"  {k:30} {v}/{total}  ({100*v//total}%)")


if __name__ == "__main__":
    main()
