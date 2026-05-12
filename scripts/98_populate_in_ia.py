"""
Script 98: Populate Indiana and Iowa per-school records.

Indiana ILEARN 2024 (= spring 2024 test = 2023-24 school year) — school-level
proficiency from ILEARN-2024-Grade3-8-Final-School.xlsx, plus biology from
ILEARN-2024-Biology-Final-School-1.xlsx.

Iowa ISASP 2024-25 — proficiency by grade × subject from
ia_isasp_{ela,math,science}_2024-25.csv. (Iowa hadn't published a discrete
2023-24 file on their portal; the 2024-25 file is the most recent available.)

Idempotent. Touches only IN + IA target school JSONs.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
RAW = ROOT / "data" / "raw"

# --- Helpers ---

def safe_float(v) -> Optional[float]:
    if v is None: return None
    s = str(v).strip().replace("%","").replace('"','').replace(",","")
    if not s or s in {"*","***","N/A","NA","NULL","<10",".","PNTS","**","-"}: return None
    try: return float(s)
    except: return None


def load_school(nces_id: str) -> dict:
    return json.loads((BY_SCHOOL / f"{nces_id}.json").read_text())


def save_school(nces_id: str, record: dict) -> None:
    record["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    (BY_SCHOOL / f"{nces_id}.json").write_text(json.dumps(record, indent=2))


# ---------------------------------------------------------------------------
# Indiana
# ---------------------------------------------------------------------------

IN_TARGETS = {
    # NCES_ID: (CSV school name match patterns)
    "180006702416": ["IN Math & Science Academy"],                     # West (the original IMSA campus)
    "180009402487": ["IN Math & Science Academy - North"],
}

YEAR_IN = "2023-24"


def parse_in_subject(csv_path: Path, school_name_idx: int = 3, prof_pct_total_idx: int = 52) -> dict[str, Optional[float]]:
    """Return {school_name: proficient_pct (0-100 scale)}."""
    if not csv_path.exists():
        return {}
    out: dict[str, Optional[float]] = {}
    with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    # Find header (row with Corp ID)
    header_row = next((i for i, r in enumerate(rows) if any("Corp ID" in (c or "") for c in r)), None)
    if header_row is None:
        return out
    for r in rows[header_row + 1:]:
        if len(r) <= prof_pct_total_idx:
            continue
        name = (r[school_name_idx] or "").strip()
        if not name:
            continue
        val = safe_float(r[prof_pct_total_idx])
        if val is None:
            continue
        # The ILEARN files store proficiency as decimals (0-1). Normalize to 0-100.
        pct = val * 100 if val <= 1.0 else val
        out[name] = round(pct, 1)
    return out


def populate_indiana() -> None:
    print("\n=== INDIANA ===")
    ela_by_school = parse_in_subject(RAW / "IN" / "in_ilearn_ela_2023-24.csv")
    math_by_school = parse_in_subject(RAW / "IN" / "in_ilearn_math_2023-24.csv")

    # Biology file has different layout (single grade, smaller)
    bio_by_school: dict[str, Optional[float]] = {}
    bio_path = RAW / "IN" / "in_ilearn_biology_2023-24.csv"
    if bio_path.exists():
        with bio_path.open(encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.reader(f))
        # Find header row (Corp ID)
        for i, r in enumerate(rows):
            if any("Corp ID" in (c or "") for c in r):
                # Find "Biology Proficient %" column
                for j, c in enumerate(r):
                    if c and "Proficient" in c and "%" in c:
                        bio_pct_idx = j
                        break
                else:
                    bio_pct_idx = None
                if bio_pct_idx is None:
                    break
                for body_row in rows[i + 1:]:
                    if len(body_row) <= bio_pct_idx:
                        continue
                    name = (body_row[3] or "").strip()
                    val = safe_float(body_row[bio_pct_idx])
                    if name and val is not None:
                        bio_by_school[name] = round(val * 100 if val <= 1.0 else val, 1)
                break

    for nces_id, patterns in IN_TARGETS.items():
        ela = math = sci = None
        for p in patterns:
            for k, v in ela_by_school.items():
                if k == p:
                    ela = v
                    break
            if ela is not None: break
        for p in patterns:
            for k, v in math_by_school.items():
                if k == p:
                    math = v
                    break
            if math is not None: break
        # Biology if present (high school only)
        for p in patterns:
            for k, v in bio_by_school.items():
                if k == p:
                    sci = v
                    break
            if sci is not None: break

        rec = load_school(nces_id)
        rec["assessment"]["year"] = YEAR_IN
        rec["assessment"]["source"] = "Indiana ILEARN"
        rec["assessment"]["ela"]["pct_proficient_all"] = ela
        rec["assessment"]["math"]["pct_proficient_all"] = math
        if sci is not None:
            rec["assessment"]["science"]["pct_proficient_all"] = sci
        rec["trends"].setdefault("ela_proficiency_by_year", {})[YEAR_IN] = ela
        rec["trends"].setdefault("math_proficiency_by_year", {})[YEAR_IN] = math
        save_school(nces_id, rec)
        print(f"  {nces_id} {patterns[0][:50]:50}  ELA={ela}  Math={math}  Bio={sci}")


# ---------------------------------------------------------------------------
# Iowa
# ---------------------------------------------------------------------------

IA_TARGETS = {
    "199902002316": ["Horizon Science Academy Des Moines"],
    "199903302345": ["Horizon Science Academy Davenport"],  # not in 2024-25 IA file
}

YEAR_IA = "2024-25"


def parse_ia_subject(csv_path: Path) -> dict[str, dict]:
    """For each school, average % proficient across all grades (weighted by Total Tested)."""
    if not csv_path.exists():
        return {}
    out: dict[str, dict] = {}
    with csv_path.open(encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    header_row = next((i for i, r in enumerate(rows) if any("School Name" in (c or "") for c in r)), None)
    if header_row is None:
        return out
    hdr = rows[header_row]
    name_idx = hdr.index("School Name")
    # Grade columns: pattern "Grade X % Proficient" + "Grade X Total Tested"
    grade_cols = []  # list of (pct_idx, total_idx)
    for j, h in enumerate(hdr):
        if h and h.endswith("% Proficient"):
            # Total Tested is the column before
            grade_cols.append((j, j - 1))
    for r in rows[header_row + 1:]:
        if len(r) <= name_idx:
            continue
        name = (r[name_idx] or "").strip()
        if not name:
            continue
        num = 0.0
        den = 0.0
        for pct_idx, tot_idx in grade_cols:
            if pct_idx >= len(r) or tot_idx >= len(r):
                continue
            pct = safe_float(r[pct_idx])
            tot = safe_float(r[tot_idx])
            if pct is None or tot is None or tot <= 0:
                continue
            num += pct * tot
            den += tot
        if den > 0:
            out[name] = {"pct": round(num / den, 1), "n": den}
    return out


def populate_iowa() -> None:
    print("\n=== IOWA ===")
    ela_data = parse_ia_subject(RAW / "IA" / "ia_isasp_ela_2024-25.csv")
    math_data = parse_ia_subject(RAW / "IA" / "ia_isasp_math_2024-25.csv")
    sci_data = parse_ia_subject(RAW / "IA" / "ia_isasp_science_2024-25.csv")

    for nces_id, patterns in IA_TARGETS.items():
        ela = math = sci = None
        for p in patterns:
            if p in ela_data:
                ela = ela_data[p]["pct"]; break
        for p in patterns:
            if p in math_data:
                math = math_data[p]["pct"]; break
        for p in patterns:
            if p in sci_data:
                sci = sci_data[p]["pct"]; break

        rec = load_school(nces_id)
        rec["assessment"]["year"] = YEAR_IA
        rec["assessment"]["source"] = "Iowa ISASP"
        rec["assessment"]["ela"]["pct_proficient_all"] = ela
        rec["assessment"]["math"]["pct_proficient_all"] = math
        if sci is not None:
            rec["assessment"]["science"]["pct_proficient_all"] = sci
        rec["trends"].setdefault("ela_proficiency_by_year", {})[YEAR_IA] = ela
        rec["trends"].setdefault("math_proficiency_by_year", {})[YEAR_IA] = math
        save_school(nces_id, rec)
        print(f"  {nces_id} {patterns[0][:50]:50}  ELA={ela}  Math={math}  Sci={sci}")


# ---------------------------------------------------------------------------

def main() -> None:
    populate_indiana()
    populate_iowa()
    print("\nDone. Re-run scripts/10_aggregate.py.")


if __name__ == "__main__":
    main()
