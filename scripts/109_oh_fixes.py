"""
Script 109: Fix OH school IRN mappings and re-run OH parsers.

Three corrections:
1. Noble Academy Euclid (NCES 390064605345) → IRN 008278 (Noble Academy-Cleveland)
2. Columbus Primary School → IRN 017123 (was sharing 133660 with HS)
3. Columbus Elementary School → IRN 009990 (was sharing 133660 with HS)

After running, the 3 Columbus campuses (HS Morse Road, Primary, Elementary) will
have distinct data and Noble Euclid will be populated.
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

# Updated map with all 17 OH schools
OH_NCES_TO_IRN = {
    "390045105010": "000825", "390051005220": "000338", "390004002939": "133629",
    "390047005029": "000858", "390045405013": "000838", "390136505544": "011533",
    "390138905567": "011986",
    "390064605345": "008278",   # Noble Academy Euclid — newly mapped
    "390004202978": "133660",   # Columbus HS Morse Road
    "390132205440": "009179",   # Columbus Middle
    "390160605963": "017123",   # Columbus Primary — newly distinct
    "390135305483": "009990",   # Columbus Elementary — newly distinct
    "390064505319": "008280",   # Noble Columbus
    "390044405003": "000808", "390136605556": "011534", "390138305625": "011976",
    "390044105000": "000804",
}


def safe_float(v):
    if v is None: return None
    s = str(v).strip().replace("%","").replace('"','').replace(",","")
    if not s or s in {"*","N/A","NA","NULL","<10",".","-","NC","PS","NR"}: return None
    if s.startswith("<="):
        try: return round(float(s[2:]) / 2.0, 1)
        except: return None
    if s.startswith(">="):
        try: return round((float(s[2:]) + 100) / 2.0, 1)
        except: return None
    try: return float(s)
    except: return None


def avg(values): nums = [v for v in values if v is not None]; return round(sum(nums)/len(nums),1) if nums else None


ELA_RE = re.compile(r"English Language Arts.*Percent Proficient|English II.*Percent Proficient", re.IGNORECASE)
MATH_RE = re.compile(r"\bMath\b.*Percent Proficient|Algebra.*Percent Proficient|Geometry.*Percent Proficient", re.IGNORECASE)
SCIENCE_RE = re.compile(r"\bScience\b.*Percent Proficient", re.IGNORECASE)


def load_by_irn(csv_path: Path, irn_col: str = "Building IRN"):
    by_irn = {}
    if not csv_path.exists(): return by_irn
    with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            irn = (row.get(irn_col) or "").strip()
            if irn: by_irn.setdefault(irn, []).append(row)
    return by_irn


def proficiency_from_ethnic(rows):
    ela_w, math_w, sci_w = [], [], []
    for row in rows:
        group = (row.get("Student Group") or "").strip().strip('"').upper()
        if group in {"", "ALL STUDENTS"}: continue
        enroll = None
        for k, v in row.items():
            if k and k.startswith("Enrollment "):
                enroll = safe_float(v); break
        if enroll is None or enroll <= 0: continue
        ela_cells, math_cells, sci_cells = [], [], []
        for col, val in row.items():
            if not col: continue
            v = safe_float(val)
            if v is None: continue
            if SCIENCE_RE.search(col): sci_cells.append(v)
            elif ELA_RE.search(col): ela_cells.append(v)
            elif MATH_RE.search(col): math_cells.append(v)
        if ela_cells: ela_w.append((sum(ela_cells)/len(ela_cells), enroll))
        if math_cells: math_w.append((sum(math_cells)/len(math_cells), enroll))
        if sci_cells: sci_w.append((sum(sci_cells)/len(sci_cells), enroll))

    def wavg(pairs):
        n = sum(v*w for v,w in pairs); d = sum(w for _,w in pairs)
        return round(n/d,1) if d>0 else None
    return wavg(ela_w), wavg(math_w), wavg(sci_w)


def main():
    print("=== OH Fixes — Noble Euclid + Columbus split ===")
    achievement = load_by_irn(RAW / "OH" / "_csv" / "oh_achievement_2023-24.csv")
    va = load_by_irn(RAW / "OH" / "_csv" / "oh_va_overview_2023-24.csv")
    ethnic = load_by_irn(RAW / "OH" / "_csv" / "oh_ethnic_2023-24.csv")
    educator = load_by_irn(RAW / "OH" / "_csv" / "oh_educator_2023-24.csv")
    grad = load_by_irn(RAW / "OH" / "_csv_grad" / "Graduation_Component.csv")

    # Trend files
    ethnic_22_23 = load_by_irn(RAW / "OH" / "_csv" / "oh_ethnic_2022-23.csv")
    ethnic_21_22 = load_by_irn(RAW / "OH" / "_csv" / "oh_ethnic_2021-22.csv")

    # Focus only on schools that changed IRN this pass
    REFRESH = {"390064605345", "390160605963", "390135305483"}
    for nces_id in REFRESH:
        irn = OH_NCES_TO_IRN[nces_id]
        rec = json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())
        rec["assessment"]["year"] = YEAR
        rec["assessment"]["source"] = "Ohio AIR / Ohio Report Card"

        # Proficiency from ethnic (race-weighted)
        ela, math, sci = proficiency_from_ethnic(ethnic.get(irn, []))
        rec["assessment"]["ela"]["pct_proficient_all"] = ela
        rec["assessment"]["math"]["pct_proficient_all"] = math
        rec["assessment"]["science"]["pct_proficient_all"] = sci

        # Achievement file: star rating + PI%
        ach_rows = achievement.get(irn, [])
        if ach_rows:
            r = ach_rows[0]
            star = (r.get("Achievement Component Star Rating") or "").strip()
            star = " ".join(star.split())
            if star:
                rec["accountability"]["year"] = YEAR
                rec["accountability"]["state_rating"] = star
            pi_pct = safe_float(r.get("Performance Index Percent 2023-2024"))
            if pi_pct is not None:
                rec["accountability"]["state_percentile_rank"] = pi_pct

        # Value-Added
        va_rows = va.get(irn, [])
        if va_rows:
            r = va_rows[0]
            rec["growth"]["year"] = YEAR
            rec["growth"]["source"] = "OH DOE"
            rec["growth"]["metric_name"] = "Value-Added Index (VAI)"
            comp = safe_float(r.get("Overall Composite"))
            if comp is not None:
                rec["growth"]["ela_growth"] = comp
                rec["growth"]["math_growth"] = comp
            star = (r.get("Progress Component Star Rating") or "").strip()
            if star:
                rec["growth"]["overall_growth_rating"] = " ".join(star.split())

        # Demographics + attendance from ethnic file
        race_map = {"WHITE, NON-HISPANIC":"white","BLACK, NON-HISPANIC":"black","HISPANIC":"hispanic","ASIAN":"asian","AMERICAN INDIAN OR ALASKAN NATIVE":"american_indian","PACIFIC ISLANDER":"pacific_islander","MULTIRACIAL":"two_or_more"}
        total = 0; att_vals = []
        for row in ethnic.get(irn, []):
            g = (row.get("Student Group") or "").strip().strip('"').upper()
            key = race_map.get(g)
            if not key: continue
            n = safe_float(row.get("Enrollment 2023-2024"))
            if n is not None:
                rec["enrollment"]["by_race_ethnicity"][key] = int(n); total += int(n)
            a = safe_float(row.get("Attendance Rate 2023-2024"))
            if a is not None: att_vals.append(a)
        if total > 0:
            rec["enrollment"]["year"] = YEAR
            rec["enrollment"]["total"] = total
        if att_vals:
            rec["attendance"]["year"] = YEAR
            rec["attendance"]["avg_daily_attendance_rate"] = avg(att_vals)

        # Educator data
        edu_rows = educator.get(irn, [])
        if edu_rows:
            r = edu_rows[0]
            rec["staff"]["year"] = YEAR
            fte = safe_float(r.get("Number of Full Time Teachers (FTE)"))
            novice = safe_float(r.get("Percent of Teachers Inexperienced"))
            temp_cred = safe_float(r.get("Percent Teachers on Temporary/Conditional Credentials"))
            if fte is not None: rec["staff"]["teacher_fte"] = fte
            if novice is not None: rec["staff"]["pct_teachers_novice"] = novice
            if temp_cred is not None: rec["staff"]["pct_teachers_certified"] = round(100 - temp_cred, 1)

        # Grad rate (for the HS, IRN-mapped or not)
        grad_rows = grad.get(irn, [])
        if grad_rows:
            r = grad_rows[0]
            four = safe_float(r.get("Four Year Graduation Rate - Class of 2023"))
            five = safe_float(r.get("Five Year Graduation Rate - Class of 2022"))
            if four is not None:
                rec["graduation"]["year"] = YEAR
                rec["graduation"]["four_year_grad_rate"] = four
            if five is not None:
                rec["graduation"]["five_year_grad_rate"] = five

        # Trends
        for year, by_irn in [("2022-23", ethnic_22_23), ("2021-22", ethnic_21_22)]:
            te, tm, _ = proficiency_from_ethnic(by_irn.get(irn, []))
            rec["trends"]["ela_proficiency_by_year"][year] = te
            rec["trends"]["math_proficiency_by_year"][year] = tm
        rec["trends"]["ela_proficiency_by_year"]["2023-24"] = ela
        rec["trends"]["math_proficiency_by_year"]["2023-24"] = math

        rec["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(rec, indent=2))
        print(f"  {nces_id} IRN={irn}  {rec['meta']['school_name'][:50]:50}  ELA={ela}  Math={math}")


if __name__ == "__main__":
    main()
