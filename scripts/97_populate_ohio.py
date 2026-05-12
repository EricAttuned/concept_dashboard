"""
Script 97: Parse Ohio raw .xlsx data and populate the 17 OH per-school records.

Ohio reports through the Building IRN system. We hand-map each Concept OH
school's NCES ID to the appropriate Building IRN (or IRNs — some schools
report under their middle-school IRN, etc.). For each school we pull:

  - Performance Index Score + Star Rating (from Achievement_Building)
  - Composite ELA & Math proficiency (from BUILDING_ETHNIC, "All Students" row)
  - Race breakouts + enrollment (from BUILDING_ETHNIC)
  - FRL%, ELL%, SpEd% (from BUILDING_ECON_DIS, BUILDING_LEP, BUILDING_DISABLED)
  - Attendance rate (from BUILDING_ETHNIC)
  - Value-Added growth score + star rating (from VA_ORG_DETAILS)
  - Prior-year Performance Index scores -> trends.{ela,math}_proficiency_by_year

Idempotent. Run after script 96.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw" / "OH" / "_csv"
YEAR = "2023-24"

# ---------------------------------------------------------------------------
# Hand-built NCES -> Building IRN map. Verified against
# data/raw/OH/_csv/oh_achievement_2023-24.csv Building Name strings.
# ---------------------------------------------------------------------------

OH_NCES_TO_IRN = {
    "390045105010": "000825",   # Horizon Science Academy Springfield (Toledo) → "Horizon Science Academy-Springfield"
    "390051005220": "000338",   # Horizon Science Academy Toledo
    "390004002939": "133629",   # Cleveland HS → "Horizon Science Acad Cleveland"
    "390047005029": "000858",   # Cleveland Elementary → "Horizon Science Academy-Cleveland Middle School"
    "390045405013": "000838",   # Denison → "Horizon Science Academy-Denison Middle School"
    "390136505544": "011533",   # Lorain
    "390138905567": "011986",   # Youngstown
    "390064605345": None,       # Noble Academy Euclid — not in current OH data
    "390004202978": "133660",   # Columbus HS Morse Road → "Horizon Science Academy Columbus"
    "390132205440": "009179",   # Columbus Middle School
    "390160605963": "133660",   # Columbus Primary (shares IRN with HS)
    "390135305483": "133660",   # Columbus Elementary (shares IRN with HS)
    "390064505319": "008280",   # Noble Academy Columbus
    "390044405003": "000808",   # Dayton Elementary → "Horizon Science Academy-Dayton"
    "390136605556": "011534",   # Dayton High School
    "390138305625": "011976",   # Dayton Downtown
    "390044105000": "000804",   # Cincinnati → "Horizon Science Academy-Cincinnati"
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace("%", "").replace('"', "").replace("$", "").replace(",", "")
    if not s or s in {"*", "N/A", "n/a", "NA", "NULL", "null", "<10", ".", "PNTS", "**", "-", "PS"}:
        return None
    if s.startswith("<="):
        try: return round(float(s[2:]) / 2.0, 1)
        except: return None
    if s.startswith(">="):
        try: return round((float(s[2:]) + 100) / 2.0, 1)
        except: return None
    try: return float(s)
    except: return None


def safe_int(v) -> Optional[int]:
    f = safe_float(v)
    return int(f) if f is not None else None


def avg(values: list[Optional[float]]) -> Optional[float]:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 1)


def load_school(nces_id: str) -> dict:
    return json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())


def save_school(nces_id: str, record: dict) -> None:
    record["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(record, indent=2))


# ---------------------------------------------------------------------------
# Loaders — index each CSV by Building IRN
# ---------------------------------------------------------------------------

def load_by_irn(csv_path: Path, irn_col: str = "Building IRN") -> dict[str, list[dict]]:
    """Return {irn: [rows]}. Rows may have multiple entries (e.g. one per Student Group)."""
    by_irn: dict[str, list[dict]] = {}
    if not csv_path.exists():
        return by_irn
    with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            irn = row.get(irn_col, "").strip()
            if not irn:
                continue
            by_irn.setdefault(irn, []).append(row)
    return by_irn


# ---------------------------------------------------------------------------
# Per-section extractors
# ---------------------------------------------------------------------------

ELA_GRADE_COL_RE = re.compile(r"English Language Arts.*Percent Proficient", re.IGNORECASE)
MATH_GRADE_COL_RE = re.compile(r"Math.*Percent Proficient", re.IGNORECASE)
SCIENCE_GRADE_COL_RE = re.compile(r"Science.*Percent Proficient", re.IGNORECASE)
HS_ELA_COL_RE = re.compile(r"High School (English|English II|English I).*Percent Proficient", re.IGNORECASE)
HS_MATH_COL_RE = re.compile(r"High School (Algebra|Geometry).*Percent Proficient", re.IGNORECASE)


def extract_proficiency(ethnic_rows: list[dict]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    The OH Ethnic file has no "All Students" row, only race-disaggregated rows.
    Compute school-level ELA/Math/Science by averaging across races, weighted by
    race enrollment.
    """
    if not ethnic_rows:
        return (None, None, None)

    ela_weighted: list[tuple[float, float]] = []
    math_weighted: list[tuple[float, float]] = []
    sci_weighted: list[tuple[float, float]] = []

    for row in ethnic_rows:
        if (row.get("Student Group") or "").strip().strip('"').upper() in {"", "ALL STUDENTS"}:
            continue
        enrollment = safe_float(row.get("Enrollment 2023-2024"))
        if enrollment is None or enrollment <= 0:
            continue

        # Average all non-null ELA cells in this row, then same for Math and Science
        ela_cells = []
        math_cells = []
        sci_cells = []
        for col, val in row.items():
            if col is None:
                continue
            v = safe_float(val)
            if v is None:
                continue
            if SCIENCE_GRADE_COL_RE.search(col):
                sci_cells.append(v)
            elif ELA_GRADE_COL_RE.search(col) or HS_ELA_COL_RE.search(col):
                ela_cells.append(v)
            elif MATH_GRADE_COL_RE.search(col) or HS_MATH_COL_RE.search(col):
                math_cells.append(v)

        if ela_cells:
            ela_weighted.append((sum(ela_cells) / len(ela_cells), enrollment))
        if math_cells:
            math_weighted.append((sum(math_cells) / len(math_cells), enrollment))
        if sci_cells:
            sci_weighted.append((sum(sci_cells) / len(sci_cells), enrollment))

    def wavg(pairs):
        if not pairs: return None
        num = sum(v * w for v, w in pairs)
        den = sum(w for _, w in pairs)
        return round(num / den, 1) if den > 0 else None

    return (wavg(ela_weighted), wavg(math_weighted), wavg(sci_weighted))


def extract_demographics(ethnic_rows: list[dict]) -> dict:
    """Extract enrollment + race breakdown from ethnic file rows. No All-Students row
    in OH ethnic file — compute total as sum of race enrollments. Attendance pulled
    from any non-null race row (they're typically the same)."""
    result: dict = {
        "total": None,
        "attendance": None,
        "by_race": {k: None for k in ("white", "black", "hispanic", "asian", "american_indian", "pacific_islander", "two_or_more")},
        "ela_sub": {k: None for k in ("black", "hispanic", "white")},
        "math_sub": {k: None for k in ("black", "hispanic", "white")},
    }
    if not ethnic_rows:
        return result

    race_map = {
        "WHITE, NON-HISPANIC": "white",
        "WHITE": "white",
        "BLACK, NON-HISPANIC": "black",
        "BLACK": "black",
        "HISPANIC": "hispanic",
        "ASIAN": "asian",
        "AMERICAN INDIAN OR ALASKAN NATIVE": "american_indian",
        "PACIFIC ISLANDER": "pacific_islander",
        "MULTIRACIAL": "two_or_more",
    }

    total = 0
    attendance_vals = []
    for row in ethnic_rows:
        group = row.get("Student Group", "").strip().strip('"').upper()
        key = race_map.get(group)
        if not key:
            continue
        n = safe_int(row.get("Enrollment 2023-2024"))
        if n is not None:
            result["by_race"][key] = n
            total += n
        att = safe_float(row.get("Attendance Rate 2023-2024"))
        if att is not None:
            attendance_vals.append(att)

        # ELA / Math subgroup composites
        ela_vals = []
        math_vals = []
        for col, val in row.items():
            if col is None:
                continue
            if ELA_GRADE_COL_RE.search(col) or HS_ELA_COL_RE.search(col):
                v = safe_float(val)
                if v is not None:
                    ela_vals.append(v)
            elif MATH_GRADE_COL_RE.search(col) or HS_MATH_COL_RE.search(col):
                v = safe_float(val)
                if v is not None:
                    math_vals.append(v)
        if key in result["ela_sub"]:
            if ela_vals:
                result["ela_sub"][key] = avg(ela_vals)
            if math_vals:
                result["math_sub"][key] = avg(math_vals)

    if total > 0:
        result["total"] = total
    if attendance_vals:
        result["attendance"] = avg(attendance_vals)
    return result


def extract_pct_in_group(rows: list[dict], target_group: str) -> Optional[float]:
    """% of enrollment matching target_group within school. Need both 'ECONDISADV' and 'NOTECONDISADV' rows."""
    for r in rows:
        if r.get("Student Group", "").strip() == target_group:
            return safe_float(r.get("Percent of Total Enrollment 2023-2024"))
    return None


def extract_va(va_rows: list[dict]) -> dict:
    """Extract Value-Added growth metrics."""
    if not va_rows:
        return {"composite": None, "effect_size": None, "star_rating": None}
    r = va_rows[0]
    return {
        "composite": safe_float(r.get("Overall Composite")),
        "effect_size": safe_float(r.get("Overall Effect Size")),
        "star_rating": (r.get("Progress Component Star Rating") or "").strip() or None,
    }


def extract_trend(achievement_rows: list[dict]) -> dict:
    """Extract performance index scores for each year as a proxy proficiency trend."""
    if not achievement_rows:
        return {}
    r = achievement_rows[0]
    out = {}
    out["2023-24"] = safe_float(r.get("Performance Index Score 2023-2024"))
    out["2022-23"] = safe_float(r.get("Performance Index Score 2022-2023"))
    out["2021-22"] = safe_float(r.get("Performance Index Score 2021-2022"))
    return out


# ---------------------------------------------------------------------------

def main() -> None:
    print("=== OHIO ===")

    achievement_by_irn = load_by_irn(RAW / "oh_achievement_2023-24.csv")
    va_by_irn = load_by_irn(RAW / "oh_va_overview_2023-24.csv")
    ethnic_by_irn = load_by_irn(RAW / "oh_ethnic_2023-24.csv")
    econ_by_irn = load_by_irn(RAW / "oh_econ_2023-24.csv")
    ell_by_irn = load_by_irn(RAW / "oh_ell_2023-24.csv")
    sped_by_irn = load_by_irn(RAW / "oh_sped_2023-24.csv")

    for nces_id, irn in OH_NCES_TO_IRN.items():
        if not irn:
            print(f"  {nces_id} SKIP (no IRN mapping)")
            continue
        rec = load_school(nces_id)
        name = rec["meta"].get("school_name", nces_id)

        # Proficiency from ethnic file (composite across grades)
        ethnic_rows = ethnic_by_irn.get(irn, [])
        ela, math, science = extract_proficiency(ethnic_rows)
        rec["assessment"]["year"] = YEAR
        rec["assessment"]["source"] = "Ohio AIR / Ohio Report Card"
        rec["assessment"]["ela"]["pct_proficient_all"] = ela
        rec["assessment"]["math"]["pct_proficient_all"] = math
        rec["assessment"]["science"]["pct_proficient_all"] = science

        # Demographics
        demo = extract_demographics(ethnic_rows)
        rec["enrollment"]["year"] = YEAR
        if demo["total"] is not None:
            rec["enrollment"]["total"] = demo["total"]
        for k, v in demo["by_race"].items():
            rec["enrollment"]["by_race_ethnicity"][k] = v
        if demo["attendance"] is not None:
            rec["attendance"]["year"] = YEAR
            rec["attendance"]["avg_daily_attendance_rate"] = demo["attendance"]

        # Subgroup proficiency
        for k in ("black", "hispanic", "white"):
            if demo["ela_sub"].get(k) is not None:
                rec["assessment"]["ela"]["by_subgroup"][k] = demo["ela_sub"][k]
            if demo["math_sub"].get(k) is not None:
                rec["assessment"]["math"]["by_subgroup"][k] = demo["math_sub"][k]

        # % FRL / ELL / SpEd from sub-files
        frl = extract_pct_in_group(econ_by_irn.get(irn, []), "ECONDISADV")
        ell = extract_pct_in_group(ell_by_irn.get(irn, []), "ENGLEARN")
        sped = extract_pct_in_group(sped_by_irn.get(irn, []), "DISABLED")
        if frl is not None:
            rec["enrollment"]["pct_free_reduced_lunch"] = frl
        if ell is not None:
            rec["enrollment"]["pct_ell"] = ell
        if sped is not None:
            rec["enrollment"]["pct_sped"] = sped

        # Growth (Value-Added)
        va = extract_va(va_by_irn.get(irn, []))
        rec["growth"]["year"] = YEAR
        rec["growth"]["source"] = "OH DOE"
        rec["growth"]["metric_name"] = "Value-Added Index (VAI)"
        if va["composite"] is not None:
            rec["growth"]["ela_growth"] = va["composite"]  # proxy — VA composite includes all subjects
            rec["growth"]["math_growth"] = va["composite"]
        if va["star_rating"]:
            rec["growth"]["overall_growth_rating"] = " ".join(va["star_rating"].split())

        # Achievement star rating → accountability state rating
        ach_rows = achievement_by_irn.get(irn, [])
        if ach_rows:
            r = ach_rows[0]
            star = (r.get("Achievement Component Star Rating") or "").strip()
            # Normalize "5  Stars" -> "5 Stars"
            star = " ".join(star.split())
            if star:
                rec["accountability"]["year"] = YEAR
                rec["accountability"]["state_rating"] = star
            pi_pct = safe_float(r.get("Performance Index Percent 2023-2024"))
            if pi_pct is not None:
                rec["accountability"]["state_percentile_rank"] = pi_pct

        # Trend: prior-year Performance Index Score (proxy for proficiency trend)
        trend = extract_trend(ach_rows)
        for y in ("2023-24", "2022-23", "2021-22"):
            v = trend.get(y)
            rec["trends"].setdefault("ela_proficiency_by_year", {})[y] = v
            rec["trends"].setdefault("math_proficiency_by_year", {})[y] = v

        save_school(nces_id, rec)
        print(f"  {nces_id} IRN={irn:>6}  {name[:48]:48}  ELA={ela}  Math={math}  VA={va['composite']}  Star={va['star_rating']}")


if __name__ == "__main__":
    main()
