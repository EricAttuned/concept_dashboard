"""
Script 203: Refresh data_manifest.json based on the ACTUAL state of each
school's JSON. Many statuses are stale ("needs_manual_download") from the
initial fetch phase even though we subsequently populated the data.

For every school, inspect what's now in by_school/<NCES>.json and write
a per-category status into the manifest:
  ok      — at least one expected field is populated for that category
  partial — category has some but not all expected fields
  missing — no fields populated (genuine data gap)
"""
from __future__ import annotations
import json, os
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BY_SCHOOL = ROOT / "data" / "by_school"
MANIFEST = ROOT / "data" / "data_manifest.json"


def has(v):
    if v is None: return False
    if isinstance(v, str): return v.strip() != ""
    if isinstance(v, (int, float)): return True
    if isinstance(v, (list, dict)): return len(v) > 0
    return bool(v)


def evaluate(rec):
    """Return {category: status} based on what's populated."""
    out = {}

    # Enrollment
    e = rec.get("enrollment", {}) or {}
    if has(e.get("total")):
        sub_count = sum(1 for k in ["pct_free_reduced_lunch","pct_ell","pct_sped"] if has(e.get(k)))
        out["enrollment"] = {"status": "ok" if sub_count >= 2 else "partial",
                              "year": e.get("year")}
    else:
        out["enrollment"] = {"status": "missing"}

    # Assessment
    a = rec.get("assessment", {}) or {}
    ela = (a.get("ela") or {}).get("pct_proficient_all")
    math = (a.get("math") or {}).get("pct_proficient_all")
    sub_ela = (a.get("ela") or {}).get("by_subgroup", {}) or {}
    has_sub = any(has(v) for v in sub_ela.values())
    if has(ela) and has(math):
        out["assessment"] = {"status": "ok" if has_sub else "partial",
                              "year": a.get("year"),
                              "ela": ela, "math": math}
    elif has(ela) or has(math):
        out["assessment"] = {"status": "partial", "year": a.get("year")}
    else:
        out["assessment"] = {"status": "missing"}

    # Attendance
    at = rec.get("attendance", {}) or {}
    if has(at.get("avg_daily_attendance_rate")) and has(at.get("chronic_absenteeism_rate")):
        out["attendance"] = {"status": "ok", "year": at.get("year")}
    elif has(at.get("avg_daily_attendance_rate")) or has(at.get("chronic_absenteeism_rate")):
        out["attendance"] = {"status": "partial", "year": at.get("year")}
    else:
        out["attendance"] = {"status": "missing"}

    # Graduation
    g = rec.get("graduation", {}) or {}
    if has(g.get("four_year_grad_rate")):
        sg = g.get("by_subgroup", {}) or {}
        has_sg = any(has(v) for v in sg.values())
        out["graduation"] = {"status": "ok" if has_sg else "partial",
                              "year": g.get("year")}
    elif rec.get("meta",{}).get("grade_band","").startswith("K-") and not "12" in rec.get("meta",{}).get("grade_band",""):
        # K-8 school — graduation not applicable
        out["graduation"] = {"status": "not_applicable", "year": g.get("year")}
    else:
        out["graduation"] = {"status": "missing"}

    # Growth
    gr = rec.get("growth", {}) or {}
    if has(gr.get("overall_growth_rating")) or has(gr.get("ela_growth")) or has(gr.get("ela_sgp")):
        out["growth"] = {"status": "ok", "year": gr.get("year")}
    else:
        out["growth"] = {"status": "missing"}

    # Accountability
    ac = rec.get("accountability", {}) or {}
    if has(ac.get("state_rating")):
        out["accountability"] = {"status": "ok", "year": ac.get("year")}
    else:
        out["accountability"] = {"status": "missing"}

    # Staff
    s = rec.get("staff", {}) or {}
    fields = [s.get("teacher_fte"), s.get("pct_teachers_certified"),
              s.get("pct_teachers_novice"), s.get("teacher_retention_rate")]
    n_pop = sum(1 for f in fields if has(f))
    if n_pop >= 3:
        out["staff"] = {"status": "ok", "year": s.get("year"), "fields_populated": n_pop}
    elif n_pop >= 1:
        out["staff"] = {"status": "partial", "year": s.get("year"), "fields_populated": n_pop}
    else:
        out["staff"] = {"status": "missing"}

    # Trends
    t = rec.get("trends", {}) or {}
    tela = t.get("ela_proficiency_by_year") or {}
    if has(tela.get("2022-23")) and has(tela.get("2021-22")):
        out["trends"] = {"status": "ok"}
    elif has(tela.get("2022-23")) or has(tela.get("2021-22")):
        out["trends"] = {"status": "partial"}
    else:
        out["trends"] = {"status": "missing"}

    return out


def main():
    manifest = json.loads(MANIFEST.read_text())
    schools = manifest.get("schools", {})

    # Rebuild from JSON state, keyed on NCES_ID
    updated = 0
    # Preserve "no_NCES" entries (newly-opened schools with no data)
    new_schools = {}
    nces_to_existing_key = {}
    for k, v in schools.items():
        flags = v.get("flags") or []
        if any("NCES ID not found" in f for f in flags) or k.startswith("MANUAL_"):
            new_schools[k] = v  # keep manual entries as-is
        else:
            nces_to_existing_key[k] = v

    # For each by_school file, refresh status
    for fn in sorted(os.listdir(BY_SCHOOL)):
        if not fn.endswith(".json"): continue
        nces = fn[:-5]
        rec = json.loads((BY_SCHOOL / fn).read_text())
        nm = rec.get("meta", {}).get("school_name", "")
        state = rec.get("meta", {}).get("state", "")
        statuses = evaluate(rec)
        existing = nces_to_existing_key.get(nces, {})
        new_schools[nces] = {
            "school_name": nm,
            "state": state,
            "region": rec.get("meta", {}).get("region"),
            "grade_band": rec.get("meta", {}).get("grade_band"),
            "data_sources": statuses,
            "flags": existing.get("flags", []),
            "last_updated": rec.get("meta", {}).get("last_updated"),
        }
        updated += 1

    manifest["schools"] = new_schools
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.write_text(json.dumps(manifest, indent=2))

    # Summary
    from collections import Counter
    total_counts = Counter()
    cat_counts = {}
    for nid, info in new_schools.items():
        for cat, st in (info.get("data_sources") or {}).items():
            s = st.get("status")
            cat_counts.setdefault(cat, Counter())[s] += 1
            total_counts[s] += 1
    print(f"Refreshed {updated} schools. Status counts (across all categories):")
    for s, c in total_counts.most_common():
        print(f"  {s:25} {c}")
    print()
    print("Per category:")
    for cat in ["enrollment","assessment","attendance","graduation","growth","accountability","staff","trends"]:
        c = cat_counts.get(cat, Counter())
        ok = c.get("ok", 0); partial = c.get("partial", 0); missing = c.get("missing", 0); na = c.get("not_applicable", 0)
        print(f"  {cat:15} ok={ok:3}  partial={partial:3}  na={na:3}  missing={missing:3}")


if __name__ == "__main__":
    main()
