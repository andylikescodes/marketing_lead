from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from marketing_lead.zcta import USER_AGENT, default_cache_dir

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def geocode_address(address: str, cache_dir: Path | None = None) -> tuple[float, float] | None:
    normalized = " ".join(address.split()).strip()
    if not normalized:
        return None

    cache_root = cache_dir or default_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = cache_root / "geocode_cache.json"
    cache = _load_cache(cache_path)
    if normalized in cache:
        value = cache[normalized]
        if value is None:
            return None
        return float(value[0]), float(value[1])

    params = urlencode(
        {
            "address": normalized,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
    )
    request = Request(
        f"{CENSUS_GEOCODER_URL}?{params}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        cache[normalized] = None
        _write_cache(cache_path, cache)
        return None

    matches = payload.get("result", {}).get("addressMatches", [])
    if not matches:
        cache[normalized] = None
        _write_cache(cache_path, cache)
        return None

    coordinates = matches[0].get("coordinates", {})
    if "x" not in coordinates or "y" not in coordinates:
        cache[normalized] = None
        _write_cache(cache_path, cache)
        return None

    value = [float(coordinates["y"]), float(coordinates["x"])]
    cache[normalized] = value
    _write_cache(cache_path, cache)
    return value[0], value[1]


def _load_cache(path: Path) -> dict[str, list[float] | None]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_cache(path: Path, cache: dict[str, list[float] | None]) -> None:
    tmp_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, sort_keys=True)
    tmp_path.replace(path)
