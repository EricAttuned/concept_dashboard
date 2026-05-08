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

### Ohio
1. Go to **https://reportcard.education.ohio.gov/download**
2. Download the ZIP files for: **Achievement**, **Progress (Value-Added)**, **Gap Closing**, and **Building Overall Summary** for the most recent school year
3. Extract CSVs into a local folder
4. Update `scripts/03_fetch_oh.py` to point `OH_DATA_URLS` at the local file paths
5. Re-run `python scripts/03_fetch_oh.py`

### Michigan
1. Go to **https://www.mischooldata.org**
2. Navigate to: *Student Performance > M-STEP* (grades 3–8) or *SAT* (grade 11)
3. Filter by school/district name, select most recent year, export CSV
4. Also pull *Student Growth > SGP* and *Accountability Scorecard* CSVs
5. Place files in `data/raw/mi/` and update path constants in `scripts/04_fetch_mi.py`
6. Re-run `python scripts/04_fetch_mi.py`

### Missouri
1. Go to **https://dese.mo.gov/data-system-management/data-download** or **https://mcds.dese.mo.gov**
2. Download **MAP Assessment Results** for the most recent year (school-level)
3. Also download the **Annual Performance Report (APR)** data
4. Place files in `data/raw/mo/` and update path constants in `scripts/05_fetch_mo.py`
5. Re-run `python scripts/05_fetch_mo.py`

### Illinois
1. Go to **https://www.isbe.net/Pages/Illinois-State-Report-Card-Data.aspx**
2. Download school-level **IAR**, **PSAT**, and **SAT** assessment data CSVs
3. Also download **SGP** (Student Growth Percentile) and **Summative Designation** files
4. Place files in `data/raw/il/` and update path constants in `scripts/06_fetch_il.py`
5. Re-run `python scripts/06_fetch_il.py`

### Iowa
1. Go to **https://educateiowa.gov/data-reporting/data-reporting/school-and-district-data**
2. Find and download **ISASP** (Iowa Statewide Assessment of Student Progress) school-level results
3. Also download the **Iowa School Performance Profile** data
4. Place files in `data/raw/ia/` and update path constants in `scripts/07_fetch_ia.py`
5. Re-run `python scripts/07_fetch_ia.py`

### Minnesota
1. Go to **https://education.mn.gov/MDE/Data/**
2. Download **MCA** (Minnesota Comprehensive Assessment) school-level results for the most recent year
3. Also download the **Multiple Measurements Rating (MMR)** and accountability data
4. Place files in `data/raw/mn/` and update path constants in `scripts/08_fetch_mn.py`
5. Re-run `python scripts/08_fetch_mn.py`

### Indiana
1. Go to **https://www.doe.in.gov/accountability/find-school-and-corporation-data-reports**
2. Download **ILEARN** school-level assessment results
3. Also download **A-F School Grades** and school-level growth data
4. Place files in `data/raw/in/` and update path constants in `scripts/09_fetch_in.py`
5. Re-run `python scripts/09_fetch_in.py`

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
