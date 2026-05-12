"""
Script 00: Build the Concept Schools master registry.

Hardcodes the 40-school seed list, then looks up each school's NCES ncessch ID
via the Urban Institute Education Data Portal CCD directory API.
Writes data/schools_master.json and updates data_manifest.json.
"""


from __future__ import annotations
import difflib
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    DATA_DIR, MASTER_PATH, get_json, iso_now, load_json, log,
    print_summary, save_json, save_manifest, load_manifest,
)

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
SCHOOLS_SEED = [
    # region, school_name, city, state, grade_band, target_region
    ("North Ohio", "Horizon Science Academy Springfield", "Toledo", "OH", "K-8", False),
    ("North Ohio", "Horizon Science Academy Springfield North", "Toledo", "OH", "K-2", False),
    ("North Ohio", "Horizon Science Academy Toledo", "Toledo", "OH", "K-12", False),
    ("North Ohio", "Horizon Science Academy Cleveland High School", "Cleveland", "OH", "9-12", False),
    ("North Ohio", "Horizon Science Academy Cleveland Elementary School", "Cleveland", "OH", "K-8", False),
    ("North Ohio", "Horizon Science Academy Denison", "Cleveland", "OH", "K-8", False),
    ("North Ohio", "Horizon Science Academy Lorain", "Lorain", "OH", "K-12", False),
    ("North Ohio", "Horizon Science Academy Lorain South", "Lorain", "OH", "K-2", False),
    ("North Ohio", "Horizon Science Academy Youngstown", "Youngstown", "OH", "K-8", False),
    ("North Ohio", "Noble Academy Euclid", "Euclid", "OH", "K-8", False),
    ("North Ohio", "Horizon Science Academy Austintown", "Youngstown", "OH", "K-2", False),
    ("Columbus", "Horizon Science Academy Columbus High School Morse Road Campus", "Columbus", "OH", "9-10", False),
    ("Columbus", "Horizon Science Academy High School Westerville Campus", "Westerville", "OH", "11-12", False),
    ("Columbus", "Horizon Science Academy Columbus Middle School", "Columbus", "OH", "6-8", False),
    ("Columbus", "Horizon Science Academy Columbus Primary School", "Columbus", "OH", "K-2", False),
    ("Columbus", "Horizon Science Academy Columbus Elementary School", "Columbus", "OH", "3-5", False),
    ("Columbus", "Noble Academy Columbus", "Columbus", "OH", "K-8", False),
    ("Columbus", "Horizon Science Academy Westerville", "Westerville", "OH", "K-6", False),
    ("Dayton/Cincinnati", "Horizon Science Academy Dayton Elementary School", "Dayton", "OH", "K-5", False),
    ("Dayton/Cincinnati", "Horizon Science Academy Dayton High School", "Dayton", "OH", "6-12", True),
    ("Dayton/Cincinnati", "Horizon Science Academy Dayton Downtown", "Dayton", "OH", "K-8", True),
    ("Dayton/Cincinnati", "Horizon Science Academy Cincinnati", "Cincinnati", "OH", "K-8", True),
    ("Michigan", "Michigan Math and Science Academy Lorraine", "Warren", "MI", "PreK-5", True),
    ("Michigan", "Michigan Math and Science Academy Dequindre", "Warren", "MI", "PreK-12", True),
    ("Michigan", "Horizon Science Academy New Bedford", "Lambertville", "MI", "PreK-8", False),
    ("Missouri", "Gateway Science Academy of St. Louis - Smiley", "St. Louis", "MO", "PreK-5", False),
    ("Missouri", "Gateway Science Academy of St. Louis - High", "St. Louis", "MO", "9-12", False),
    ("Missouri", "Gateway Science Academy of St. Louis - Middle", "St. Louis", "MO", "6-8", False),
    ("Missouri", "Gateway Science Academy of St. Louis - South", "St. Louis", "MO", "PreK-5", False),
    ("Illinois", "Chicago Math and Science Academy", "Chicago", "IL", "6-12", False),
    ("Illinois", "Horizon Science Academy Belmont", "Chicago", "IL", "K-11", False),
    ("Illinois", "Horizon Science Academy McKinley Park", "Chicago", "IL", "K-12", False),
    ("Illinois", "Horizon Science Academy Southwest Chicago", "Chicago", "IL", "K-12", False),
    ("Iowa", "Horizon Science Academy Des Moines", "Des Moines", "IA", "PreK-6", False),
    ("Iowa", "Horizon Science Academy Davenport", "Davenport", "IA", "K-6", False),
    ("Minnesota", "Minnesota Math and Science Academy", "Saint Paul", "MN", "K-12", True),
    ("Minnesota", "Horizon Science Academy Twin Cities", "Minneapolis", "MN", "K-8", True),
    ("Indiana", "Indiana Math and Science Academy West", "Indianapolis", "IN", "K-8", False),
    ("Indiana", "Indiana Math and Science Academy North", "Indianapolis", "IN", "K-12", False),
    ("Indiana", "Indiana Math and Science Academy Central", "Indianapolis", "IN", "K-6", False),
]

BASE_URL = "https://educationdata.urban.org/api/v1/schools/ccd/directory/"

STATE_FIPS = {
    "OH": "39", "MI": "26", "MO": "29", "IL": "17",
    "IA": "19", "MN": "27", "IN": "18",
}


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return s.lower().strip()


def name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def search_school(name: str, city: str, state: str) -> tuple[str | None, str | None, float]:
    """
    Search CCD directory for a school by name+state.
    Returns (ncessch, matched_name, confidence_score).
    """
    fips = STATE_FIPS.get(state)
    params = {
        "fips": fips,
        "school_name": name,
        "per_page": 10,
        "page": 1,
    }
    data = get_json(BASE_URL, params=params)
    if data and data.get("results"):
        results = data["results"]
        # Score candidates by name similarity + city match
        best = None
        best_score = 0.0
        for r in results:
            sim = name_similarity(name, r.get("school_name", ""))
            city_bonus = 0.1 if normalize(city) in normalize(r.get("city", "")) else 0.0
            score = sim + city_bonus
            if score > best_score:
                best_score = score
                best = r
        if best and best_score >= 0.55:
            return best.get("ncessch"), best.get("school_name"), best_score

    # Fallback: search by city
    params2 = {
        "fips": fips,
        "city": city.upper(),
        "per_page": 50,
        "page": 1,
    }
    data2 = get_json(BASE_URL, params=params2)
    if data2 and data2.get("results"):
        best = None
        best_score = 0.0
        for r in data2["results"]:
            sim = name_similarity(name, r.get("school_name", ""))
            if sim > best_score:
                best_score = sim
                best = r
        if best and best_score >= 0.60:
            return best.get("ncessch"), best.get("school_name"), best_score

    return None, None, 0.0


def build_master():
    updated = skipped = failed = 0
    schools_out = []

    # If master already exists, index existing records for idempotency
    existing = {s["school_name"]: s for s in load_json(MASTER_PATH).get("schools", [])}

    manifest = load_manifest()
    manifest.setdefault("schools", {})

    print(f"\n{'='*70}")
    print("NCES ID Lookup Results")
    print(f"{'='*70}")
    print(f"{'School Name':<55} {'NCES ID':<14} {'Conf':>5} {'Status'}")
    print(f"{'-'*70}")

    for region, name, city, state, grade_band, target in SCHOOLS_SEED:
        seed_key = name

        if seed_key in existing and existing[seed_key].get("nces_id"):
            record = existing[seed_key]
            schools_out.append(record)
            skipped += 1
            print(f"{name:<55} {record['nces_id']:<14} {'--':>5} (cached)")
            continue

        nces_id, matched_name, conf = search_school(name, city, state)

        if nces_id:
            status = "ok" if conf >= 0.75 else "low_confidence"
            record = {
                "region": region,
                "school_name": name,
                "city": city,
                "state": state,
                "grade_band": grade_band,
                "target_region": target,
                "nces_id": nces_id,
                "nces_matched_name": matched_name,
                "nces_match_confidence": round(conf, 3),
                "needs_manual_nces_lookup": conf < 0.75,
            }
            conf_str = f"{conf:.2f}"
            flag = " *** LOW CONF" if conf < 0.75 else ""
            print(f"{name:<55} {nces_id:<14} {conf_str:>5}{flag}")

            mentry = manifest["schools"].setdefault(nces_id, {
                "school_name": name,
                "state": state,
                "data_sources": {},
                "flags": [],
            })
            if conf < 0.75:
                flags = mentry.setdefault("flags", [])
                if "Low-confidence NCES match — verify manually" not in flags:
                    flags.append("Low-confidence NCES match — verify manually")
            updated += 1
        else:
            record = {
                "region": region,
                "school_name": name,
                "city": city,
                "state": state,
                "grade_band": grade_band,
                "target_region": target,
                "nces_id": None,
                "nces_matched_name": None,
                "nces_match_confidence": 0.0,
                "needs_manual_nces_lookup": True,
            }
            print(f"{name:<55} {'NOT FOUND':<14} {'0.00':>5} *** MANUAL NEEDED")
            failed += 1

            # Add placeholder manifest entry so dashboard can still reference school
            placeholder_key = f"MANUAL_{state}_{name[:20].replace(' ', '_')}"
            mentry = manifest["schools"].setdefault(placeholder_key, {
                "school_name": name,
                "state": state,
                "data_sources": {},
                "flags": ["NCES ID not found — manual lookup required"],
            })

        schools_out.append(record)

    print(f"{'-'*70}\n")

    master = {
        "generated_at": iso_now(),
        "total_schools": len(schools_out),
        "schools": schools_out,
    }
    save_json(MASTER_PATH, master)
    log.info("Wrote %s", MASTER_PATH)

    manifest["generated_at"] = iso_now()
    save_manifest(manifest)

    print_summary("00_build_master_list", updated, skipped, failed)
    return updated, skipped, failed


if __name__ == "__main__":
    build_master()
