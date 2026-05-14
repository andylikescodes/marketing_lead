from __future__ import annotations

import csv
import io
import os
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from marketing_lead.models import ZipLocation

CENSUS_ZCTA_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2025_Gazetteer/2025_Gaz_zcta_national.zip"
)
USER_AGENT = "marketing-lead-prototype/0.1"


def default_cache_dir() -> Path:
    return Path(os.environ.get("MARKETING_LEAD_CACHE", "~/.cache/marketing_lead")).expanduser()


def lookup_zip_centroid(zip_code: str, cache_dir: Path | None = None) -> ZipLocation:
    normalized = _normalize_zip(zip_code)
    records = _load_zcta_records(cache_dir or default_cache_dir())
    try:
        record = records[normalized]
    except KeyError as exc:
        raise ValueError(f"ZIP/ZCTA {zip_code!r} was not found in the Census Gazetteer file.") from exc

    return ZipLocation(
        zip_code=normalized,
        latitude=float(record["INTPTLAT"]),
        longitude=float(record["INTPTLONG"]),
        source="US Census 2025 ZCTA Gazetteer",
    )


def _normalize_zip(zip_code: str) -> str:
    digits = "".join(ch for ch in zip_code if ch.isdigit())
    if len(digits) != 5:
        raise ValueError("ZIP code must contain exactly five digits.")
    return digits


def _load_zcta_records(cache_dir: Path) -> dict[str, dict[str, str]]:
    txt_path = cache_dir / "2025_Gaz_zcta_national.txt"
    if not txt_path.exists():
        _download_zcta_file(cache_dir, txt_path)

    with txt_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="|")
        return {row["GEOID"]: row for row in reader}


def _download_zcta_file(cache_dir: Path, txt_path: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    request = Request(CENSUS_ZCTA_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        payload = response.read()

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = [name for name in archive.namelist() if name.endswith(".txt")]
        if len(members) != 1:
            raise RuntimeError("Unexpected Census Gazetteer archive layout.")
        txt_path.write_bytes(archive.read(members[0]))
