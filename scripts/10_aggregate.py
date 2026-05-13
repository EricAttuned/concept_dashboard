"""
Script 10: Aggregate all school JSON files into network.json and by_region.json.

Reads data/by_school/{nces_id}.json for every school in schools_master.json.
Computes enrollment totals, weighted-average proficiency, demographic breakdowns,
and accountability rating distributions — at both network and region level.

Null values are excluded from averages (not treated as 0).
"""


from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    AGGREGATED_DIR, BY_SCHOOL_DIR, iso_now, load_json, load_master,
    log, print_summary, save_json, MANIFEST_PATH,
)


def weighted_avg(pairs: list[tuple[float, float]]) -> float | None:
    """Weighted average from (value, weight) pairs; excludes None values."""
    valid = [(v, w) for v, w in pairs if v is not None and w is not None and w > 0]
    if not valid:
        return None
    total_weight = sum(w for _, w in valid)
    if total_weight == 0:
        return None
    return round(sum(v * w for v, w in valid) / total_weight, 1)


def safe_get(d: dict | None, *keys, default=None):
    """Safely traverse nested dict."""
    current = d
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k)
    return current if current is not None else default


def build_school_metrics(record: dict) -> dict:
    """Extract the key metrics from a school record for aggregation."""
    enrollment = safe_get(record, "enrollment", "total")
    ela = safe_get(record, "assessment", "ela", "pct_proficient_all")
    math = safe_get(record, "assessment", "math", "pct_proficient_all")
    sci = safe_get(record, "assessment", "science", "pct_proficient_all")
    growth_rating = safe_get(record, "growth", "overall_growth_rating")
    accountability = safe_get(record, "accountability", "state_rating")
    frl = safe_get(record, "enrollment", "pct_free_reduced_lunch")
    ell = safe_get(record, "enrollment", "pct_ell")
    sped = safe_get(record, "enrollment", "pct_sped")
    teacher_fte = safe_get(record, "staff", "teacher_fte")
    pct_certified = safe_get(record, "staff", "pct_teachers_certified")
    grad_4yr = safe_get(record, "graduation", "four_year_grad_rate")
    race = safe_get(record, "enrollment", "by_race_ethnicity") or {}

    # Prior-year proficiency for trend aggregation
    trends = record.get("trends") or {}
    trends_ela = trends.get("ela_proficiency_by_year") or {}
    trends_math = trends.get("math_proficiency_by_year") or {}

    return {
        "enrollment": enrollment,
        "ela_pct": ela,
        "math_pct": math,
        "sci_pct": sci,
        "growth_rating": growth_rating,
        "accountability": accountability,
        "frl_pct": frl,
        "ell_pct": ell,
        "sped_pct": sped,
        "teacher_fte": teacher_fte,
        "pct_certified": pct_certified,
        "grad_4yr": grad_4yr,
        "race": race,
        "assessment_year": safe_get(record, "assessment", "year"),
        "trends_ela": trends_ela,
        "trends_math": trends_math,
    }


def aggregate_group(schools_with_metrics: list[tuple[dict, dict]]) -> dict:
    """
    Aggregate a group of (school_meta, metrics) pairs into rollup stats.
    school_meta = dict from schools_master
    metrics = dict from build_school_metrics
    """
    total_enrollment = 0
    ela_pairs = []
    math_pairs = []
    fte_total = 0.0
    cert_pairs = []
    grad_pairs = []
    accountability_dist = {}
    growth_dist = {}
    race_totals = {
        "american_indian": 0, "asian": 0, "black": 0, "hispanic": 0,
        "pacific_islander": 0, "two_or_more": 0, "white": 0,
    }
    assessment_years = set()

    schools_with_ela = 0
    schools_with_math = 0
    schools_with_growth = 0
    schools_with_accountability = 0

    # Year-over-year proficiency aggregation
    trend_years = ["2021-22", "2022-23", "2023-24"]
    trend_ela: dict[str, list[tuple[float, float]]] = {y: [] for y in trend_years}
    trend_math: dict[str, list[tuple[float, float]]] = {y: [] for y in trend_years}

    for meta, m in schools_with_metrics:
        enroll = m["enrollment"] or 0
        total_enrollment += enroll

        for y in trend_years:
            v = (m.get("trends_ela") or {}).get(y)
            if v is not None:
                trend_ela[y].append((v, enroll or 1))
            v = (m.get("trends_math") or {}).get(y)
            if v is not None:
                trend_math[y].append((v, enroll or 1))

        if m["ela_pct"] is not None:
            ela_pairs.append((m["ela_pct"], enroll or 1))
            schools_with_ela += 1
        if m["math_pct"] is not None:
            math_pairs.append((m["math_pct"], enroll or 1))
            schools_with_math += 1
        if m["teacher_fte"] is not None:
            fte_total += m["teacher_fte"]
        if m["pct_certified"] is not None:
            cert_pairs.append((m["pct_certified"], 1))
        if m["grad_4yr"] is not None:
            grad_pairs.append((m["grad_4yr"], 1))
        if m["accountability"]:
            accountability_dist[m["accountability"]] = accountability_dist.get(m["accountability"], 0) + 1
            schools_with_accountability += 1
        if m["growth_rating"]:
            growth_dist[m["growth_rating"]] = growth_dist.get(m["growth_rating"], 0) + 1
            schools_with_growth += 1
        if m["assessment_year"]:
            assessment_years.add(m["assessment_year"])

        for race_key in race_totals:
            val = (m["race"] or {}).get(race_key)
            if val is not None:
                race_totals[race_key] += val

    total_schools = len(schools_with_metrics)

    return {
        "total_schools": total_schools,
        "total_enrollment": total_enrollment,
        "ela_proficiency_weighted_avg": weighted_avg(ela_pairs),
        "ela_proficiency_schools_included": schools_with_ela,
        "math_proficiency_weighted_avg": weighted_avg(math_pairs),
        "math_proficiency_schools_included": schools_with_math,
        "teacher_fte_total": round(fte_total, 1) if fte_total else None,
        "pct_teachers_certified_avg": weighted_avg(cert_pairs),
        "grad_rate_4yr_avg": weighted_avg(grad_pairs),
        "accountability_distribution": accountability_dist,
        "growth_rating_distribution": growth_dist,
        "schools_with_growth_data": schools_with_growth,
        "schools_with_accountability": schools_with_accountability,
        "race_ethnicity_totals": race_totals,
        "assessment_years_present": sorted(assessment_years),
        "trends": {
            "ela_proficiency_by_year": {y: weighted_avg(trend_ela[y]) for y in trend_years},
            "math_proficiency_by_year": {y: weighted_avg(trend_math[y]) for y in trend_years},
            "ela_schools_per_year": {y: len(trend_ela[y]) for y in trend_years},
            "math_schools_per_year": {y: len(trend_math[y]) for y in trend_years},
        },
    }


def main():
    schools = load_master()
    if not schools:
        log.error("No schools in master list")
        sys.exit(1)

    all_school_metrics = []
    region_buckets: dict[str, list] = {}
    skipped = failed = 0

    for school in schools:
        nces_id = school.get("nces_id")
        if not nces_id:
            log.warning("Skipping %s — no NCES ID", school.get("school_name"))
            skipped += 1
            continue

        path = BY_SCHOOL_DIR / f"{nces_id}.json"
        if not path.exists():
            log.warning("No data file for %s (%s)", school["school_name"], nces_id)
            skipped += 1
            continue

        try:
            record = load_json(path)
            metrics = build_school_metrics(record)
            pair = (school, metrics)
            all_school_metrics.append(pair)

            region = school.get("region", "Unknown")
            region_buckets.setdefault(region, []).append(pair)
        except Exception as exc:
            log.error("Error processing %s: %s", school.get("school_name"), exc)
            failed += 1

    # ── Network-level rollup ─────────────────────────────────────
    network = {
        "generated_at": iso_now(),
        **aggregate_group(all_school_metrics),
        "schools": [
            {
                "nces_id": m.get("meta", {}).get("nces_id") or s.get("nces_id"),
                "school_name": s["school_name"],
                "region": s["region"],
                "state": s["state"],
                "grade_band": s["grade_band"],
                "target_region": s["target_region"],
                "enrollment": met["enrollment"],
                "ela_pct": met["ela_pct"],
                "math_pct": met["math_pct"],
                "growth_rating": met["growth_rating"],
                "accountability": met["accountability"],
                "assessment_year": met["assessment_year"],
            }
            for s, met in all_school_metrics
            for m in [load_json(BY_SCHOOL_DIR / f"{s['nces_id']}.json")]
        ],
    }
    save_json(AGGREGATED_DIR / "network.json", network)
    log.info("Wrote network.json (%d schools)", len(all_school_metrics))

    # ── Region-level rollup ──────────────────────────────────────
    by_region = {
        "generated_at": iso_now(),
        "regions": {},
    }
    for region, pairs in region_buckets.items():
        by_region["regions"][region] = {
            **aggregate_group(pairs),
            "schools": [s["school_name"] for s, _ in pairs],
        }
    save_json(AGGREGATED_DIR / "by_region.json", by_region)
    log.info("Wrote by_region.json (%d regions)", len(by_region["regions"]))

    # ── Update manifest network summary ─────────────────────────
    from utils import load_manifest, save_manifest
    manifest = load_manifest()
    manifest["generated_at"] = iso_now()
    total = len(schools)
    needs_manual = sum(
        1 for entry in manifest.get("schools", {}).values()
        if any(
            src.get("status") == "needs_manual_download"
            for src in entry.get("data_sources", {}).values()
        )
    )
    schools_full = sum(
        1 for entry in manifest.get("schools", {}).values()
        if all(
            src.get("status") == "ok"
            for src in entry.get("data_sources", {}).values()
        ) and entry.get("data_sources")
    )
    states_attention = list({
        entry.get("state")
        for entry in manifest.get("schools", {}).values()
        if any(
            src.get("status") in ("needs_manual_download", "error")
            for src in entry.get("data_sources", {}).values()
        )
    })
    manifest["network_summary"] = {
        "total_schools": total,
        "schools_with_full_data": schools_full,
        "schools_needing_manual_update": needs_manual,
        "oldest_data_year": None,
        "states_needing_attention": sorted(s for s in states_attention if s),
    }
    save_manifest(manifest)
    log.info("Updated manifest network_summary")

    updated = len(all_school_metrics)
    print_summary("10_aggregate", updated, skipped, failed)


if __name__ == "__main__":
    main()
