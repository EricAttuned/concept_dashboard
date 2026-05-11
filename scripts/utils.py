"""Shared helpers for the Concept Schools data pipeline."""

import json
import os
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
BY_SCHOOL_DIR = DATA_DIR / "by_school"
AGGREGATED_DIR = DATA_DIR / "aggregated"
MANIFEST_PATH = DATA_DIR / "data_manifest.json"
MASTER_PATH = DATA_DIR / "schools_master.json"

UA = "ConceptSchoolsDashboard/1.0 (education research; attunededucation.com)"
NCES_SUPPRESSION = {-1, -2, -9, "-1", "-2", "-9"}
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 0.1  # 10 req/sec

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("concept")


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": UA})
    return session


SESSION = make_session()


def get_json(url: str, params: Optional[dict] = None, session: Optional[requests.Session] = None) -> Optional[dict]:
    s = session or SESSION
    time.sleep(RATE_LIMIT_DELAY)
    try:
        r = s.get(url, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as exc:
        log.warning("GET %s failed: %s", url, exc)
        return None


def load_raw_csv(state: str, keyword: str = "") -> Optional[list]:
    """
    Look for a CSV or ZIP file in data/raw/{state}/ whose filename contains
    `keyword` (case-insensitive). Returns list of row dicts, or None if not found.
    Searches all files if keyword is empty, returning rows from the first CSV found.
    """
    import csv as _csv
    import zipfile as _zip
    raw_dir = ROOT / "data" / "raw" / state
    if not raw_dir.exists():
        return None

    candidates = sorted(raw_dir.iterdir())
    for path in candidates:
        name_lower = path.name.lower()
        if keyword and keyword.lower() not in name_lower:
            continue
        try:
            if path.suffix.lower() == ".zip":
                with _zip.ZipFile(path) as zf:
                    csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                    if not csv_names:
                        continue
                    with zf.open(csv_names[0]) as cf:
                        text = cf.read().decode("utf-8-sig", errors="replace")
                        rows = list(_csv.DictReader(__import__("io").StringIO(text)))
                        if rows:
                            log.info("Loaded %d rows from %s (ZIP)", len(rows), path.name)
                            return rows
            elif path.suffix.lower() in (".csv", ".txt"):
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                rows = list(_csv.DictReader(__import__("io").StringIO(text)))
                if rows:
                    log.info("Loaded %d rows from %s", len(rows), path.name)
                    return rows
        except Exception as exc:
            log.warning("Could not read %s: %s", path, exc)

    return None


def nces_val(v: Any) -> Optional[Any]:
    """Return None for NCES suppression codes, otherwise return the value."""
    if v in NCES_SUPPRESSION:
        return None
    try:
        if int(v) in {-1, -2, -9}:
            return None
    except (TypeError, ValueError):
        pass
    return v


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path: Path, data: dict, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, default=str)


def load_school(nces_id: str) -> dict:
    path = BY_SCHOOL_DIR / f"{nces_id}.json"
    return load_json(path)


def save_school(nces_id: str, record: dict) -> None:
    path = BY_SCHOOL_DIR / f"{nces_id}.json"
    existing = load_json(path)
    merged = _deep_merge(existing, record)
    save_json(path, merged)


def _deep_merge(base: dict, update: dict) -> dict:
    """Merge update into base; update wins on scalar conflicts; recurse into dicts."""
    result = dict(base)
    for k, v in update.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        elif v is not None:
            result[k] = v
        elif k not in result:
            result[k] = v
    return result


def load_manifest() -> dict:
    return load_json(MANIFEST_PATH)


def save_manifest(manifest: dict) -> None:
    save_json(MANIFEST_PATH, manifest)


def update_manifest_school(nces_id: str, school_name: str, state: str,
                            source_key: str, status: str, year: Optional[str] = None,
                            manual_url: Optional[str] = None,
                            flags: Optional[list] = None) -> None:
    manifest = load_manifest()
    schools = manifest.setdefault("schools", {})
    entry = schools.setdefault(nces_id, {
        "school_name": school_name,
        "state": state,
        "data_sources": {},
        "flags": [],
    })
    src = entry["data_sources"].setdefault(source_key, {})
    src["status"] = status
    src["last_fetched"] = datetime.utcnow().date().isoformat()
    if year:
        src["year"] = year
    if manual_url:
        src["manual_url"] = manual_url
    if flags:
        existing_flags = entry.get("flags", [])
        for flag in flags:
            if flag not in existing_flags:
                existing_flags.append(flag)
        entry["flags"] = existing_flags
    save_manifest(manifest)


def iso_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def load_master() -> list:
    data = load_json(MASTER_PATH)
    return data.get("schools", [])


def year_label(year_int: int) -> str:
    """Convert e.g. 2023 → '2023-24'."""
    return f"{year_int}-{str(year_int + 1)[-2:]}"


def print_summary(script_name: str, updated: int, skipped: int, failed: int) -> None:
    print(f"\n{'='*60}")
    print(f"{script_name} complete: {updated} updated, {skipped} skipped, {failed} failed")
    print(f"{'='*60}\n")
