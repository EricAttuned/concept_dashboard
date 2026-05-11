# Concept Schools Network Dashboard

A data pipeline and interactive HTML dashboard for the Concept Schools charter network (~40 schools across OH, MI, MO, IL, IA, MN, IN). Built for internal analysis by Attuned Education Partners.

## Project Structure

```
concept-dashboard/
├── index.html                    # Self-contained dashboard (open in browser)
├── requirements.txt
├── data/
│   ├── schools_master.json       # Master registry with NCES IDs
│   ├── data_manifest.json        # Source status and data freshness tracking
│   ├── by_school/                # One JSON per school (named by NCES ID)
│   └── aggregated/
│       ├── network.json          # Network-wide rollups
│       └── by_region.json        # Region-level rollups
├── scripts/
│   ├── utils.py                  # Shared helpers
│   ├── 00_build_master_list.py   # NCES ID lookup
│   ├── 01_fetch_nces_ccd.py      # Enrollment + staff (federal)
│   ├── 02_fetch_edfacts.py       # Graduation + federal assessment baseline
│   ├── 03_fetch_oh.py            # Ohio: AIR assessment, Value-Added, report card
│   ├── 04_fetch_mi.py            # Michigan: M-STEP, SGP, accountability
│   ├── 05_fetch_mo.py            # Missouri: MAP assessment, APR
│   ├── 06_fetch_il.py            # Illinois: IAR/PSAT/SAT, ISBE
│   ├── 07_fetch_ia.py            # Iowa: ISASP
│   ├── 08_fetch_mn.py            # Minnesota: MCA, MMR
│   ├── 09_fetch_in.py            # Indiana: ILEARN, A-F accountability
│   └── 10_aggregate.py           # Roll up all schools into network/region JSONs
└── schema/
    └── school_record.json        # Canonical JSON schema with field definitions
```

## Setup

```bash
pip install -r requirements.txt
```

Python 3.10+ required.

## Running the Full Pipeline

Run scripts in order from the project root directory:

```bash
python scripts/00_build_master_list.py   # Builds schools_master.json with NCES IDs
python scripts/01_fetch_nces_ccd.py      # Enrollment, demographics, staff from NCES
python scripts/02_fetch_edfacts.py       # Federal graduation rates + assessment baseline
python scripts/03_fetch_oh.py            # Ohio state data
python scripts/04_fetch_mi.py            # Michigan state data
python scripts/05_fetch_mo.py            # Missouri state data
python scripts/06_fetch_il.py            # Illinois state data
python scripts/07_fetch_ia.py            # Iowa state data
python scripts/08_fetch_mn.py            # Minnesota state data
python scripts/09_fetch_in.py            # Indiana state data
python scripts/10_aggregate.py           # Build network.json and by_region.json
```

Then open `index.html` in a browser (no web server needed for local use; if served via HTTP all relative data paths resolve automatically).

## Running a Single State Update

To refresh just one state without touching other schools' data:

```bash
python scripts/03_fetch_oh.py   # re-runs Ohio only
python scripts/10_aggregate.py  # re-aggregate after any state update
```

Each script is **idempotent** — safe to re-run. It merges new data into existing school JSON files (never replaces a field with null if a value already exists).

## Manual Download Instructions

Several state portals require manual navigation or file download. Check `data/data_manifest.json` for which schools need attention (`"status": "needs_manual_download"`). The Data Status tab in the dashboard also shows this at a glance.

### How the drop-in folder works

Each state script checks for local files **before** attempting any URL fetch. The workflow is always the same:

1. Download the CSV (or ZIP containing a CSV) from the state portal
2. Drop the file into `data/raw/{STATE}/` — **no renaming required**
3. Re-run the state script: `python scripts/0X_fetch_XX.py`
4. Re-run aggregation: `python scripts/10_aggregate.py`

The script picks up any CSV in the folder automatically. If you have multiple files (e.g. Achievement + Progress), drop them all in — the script will read the first one that matches the expected keyword in the filename, then fall back to the first CSV found.

```
data/raw/
├── OH/   ← drop Ohio Report Card CSVs/ZIPs here
├── MI/   ← drop MI School Data M-STEP export here
├── MO/   ← drop Missouri MAP assessment CSV here
├── IL/   ← drop ISBE IAR/assessment CSV here
├── IA/   ← drop Iowa ISASP CSV here
├── MN/   ← drop Minnesota MCA CSV here
└── IN/   ← drop Indiana ILEARN CSV here
```

> **Note:** Files in `data/raw/` are git-ignored (they can be large). The empty folders are tracked via `.gitkeep` files.

---

### Ohio
1. Go to **https://reportcard.education.ohio.gov/download**
2. Download the ZIP/CSV for **Achievement** (and optionally Progress, Gap Closing, Overall Summary)
3. Drop into `data/raw/OH/`
4. Re-run `python scripts/03_fetch_oh.py`

### Michigan
1. Go to **https://www.mischooldata.org**
2. Navigate to: *Student Performance > M-STEP* (grades 3–8) or *SAT* (grade 11)
3. Filter by school/district, select most recent year, export CSV
4. Drop into `data/raw/MI/`
5. Re-run `python scripts/04_fetch_mi.py`

### Missouri
1. Go to **https://dese.mo.gov/data-system-management/data-download** or **https://mcds.dese.mo.gov**
2. Download **MAP Assessment Results** for the most recent year (school-level)
3. Drop into `data/raw/MO/`
4. Re-run `python scripts/05_fetch_mo.py`

### Illinois
1. Go to **https://www.isbe.net/Pages/Illinois-State-Report-Card-Data.aspx**
2. Download school-level **IAR** assessment CSV (or PSAT/SAT for high school grades)
3. Drop into `data/raw/IL/`
4. Re-run `python scripts/06_fetch_il.py`

### Iowa
1. Go to **https://educateiowa.gov/data-reporting/data-reporting/school-and-district-data**
2. Download **ISASP** (Iowa Statewide Assessment of Student Progress) school-level results
3. Drop into `data/raw/IA/`
4. Re-run `python scripts/07_fetch_ia.py`

### Minnesota
1. Go to **https://education.mn.gov/MDE/Data/**
2. Download **MCA** (Minnesota Comprehensive Assessment) school-level results
3. Drop into `data/raw/MN/`
4. Re-run `python scripts/08_fetch_mn.py`

### Indiana
1. Go to **https://www.doe.in.gov/accountability/find-school-and-corporation-data-reports**
2. Download **ILEARN** school-level assessment results
3. Drop into `data/raw/IN/`
4. Re-run `python scripts/09_fetch_in.py`

## Adding a New School Year

1. Update `schools_master.json` if any schools opened or closed
2. Update the target year constant in each state script (e.g., `YEAR = "2023-24"`)
3. Run the full pipeline from script 00 onward
4. Check `data_manifest.json` for any new gaps

## Adding a New School

1. Add the school's entry to `SCHOOLS_SEED` in `scripts/00_build_master_list.py`
2. Run `python scripts/00_build_master_list.py` to look up its NCES ID
3. If the NCES lookup fails, manually look up the 12-digit NCES ID at https://nces.ed.gov/ccd/schoolsearch/ and add it to `data/schools_master.json`
4. Run the appropriate state script and `python scripts/10_aggregate.py`

## Schema Reference

See `schema/school_record.json` for the complete JSON Schema with all field definitions, types, and descriptions.

Key fields per school record:
- `meta` — school identity (NCES ID, name, region, state, grade band)
- `enrollment` — total enrollment, by grade, by race/ethnicity, FRL%/ELL%/SPED%
- `staff` — teacher FTE, certification rate, novice rate, retention
- `assessment` — ELA and Math proficiency overall and by subgroup
- `growth` — growth metric (state-specific: VAI, SGP, MMR, etc.)
- `graduation` — 4-year and 5-year graduation rates by subgroup
- `attendance` — daily attendance rate, chronic absenteeism
- `accountability` — state rating, percentile rank
- `trends` — 3-year proficiency history

## Data Notes

- **NCES suppression codes** (-1, -2, -9) are stored as `null` and flagged in the manifest
- **EDFacts data** lags 1–2 years; used as a federal baseline / cross-check
- **State assessment data** is the primary source; state scripts overwrite EDFacts values for assessment fields
- Schools with `"needs_manual_nces_lookup": true` in `schools_master.json` must be resolved before their federal data can be fetched
