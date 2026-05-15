from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from marketing_lead.zcta import USER_AGENT, default_cache_dir

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


@dataclass(frozen=True)
class GeocodeResult:
    latitude: float
    longitude: float
    matched_address: str = ""
    match_confidence: str = ""
    source: str = "census_geocoder"


def geocode_address(address: str, cache_dir: Path | None = None) -> tuple[float, float] | None:
    result = geocode_address_details(address, cache_dir=cache_dir)
    if not result:
        return None
    return result.latitude, result.longitude


def geocode_address_details(address: str, cache_dir: Path | None = None) -> GeocodeResult | None:
    normalized = " ".join(address.split()).strip()
    if not normalized:
        return None

    cache_root = cache_dir or default_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = cache_root / "geocode_cache.json"
    cache = _load_cache(cache_path)
    if normalized in cache:
        value = cache[normalized]
        return _decode_cache_result(value)

    params = urlencode({"address": normalized, "benchmark": "Public_AR_Current", "format": "json"})
    request = Request(
        f"{CENSUS_GEOCODER_URL}?{params}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )

    payload = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception:
            if attempt == 2:
                cache[normalized] = None
                _write_cache(cache_path, cache)
                return None
            time.sleep(0.3 * (2**attempt))

    matches = (payload or {}).get("result", {}).get("addressMatches", [])
    if not matches:
        cache[normalized] = None
        _write_cache(cache_path, cache)
        return None

    match = matches[0]
    coordinates = match.get("coordinates", {})
    if "x" not in coordinates or "y" not in coordinates:
        cache[normalized] = None
        _write_cache(cache_path, cache)
        return None

    result = GeocodeResult(
        latitude=float(coordinates["y"]),
        longitude=float(coordinates["x"]),
        matched_address=str(match.get("matchedAddress") or ""),
        match_confidence=str(match.get("tigerLine", {}).get("side") or ""),
    )
    cache[normalized] = {
        "latitude": result.latitude,
        "longitude": result.longitude,
        "matched_address": result.matched_address,
        "match_confidence": result.match_confidence,
        "source": result.source,
    }
    _write_cache(cache_path, cache)
    return result


def _decode_cache_result(value: object) -> GeocodeResult | None:
    if value is None:
        return None
    if isinstance(value, list) and len(value) == 2:
        return GeocodeResult(latitude=float(value[0]), longitude=float(value[1]))
    if isinstance(value, dict):
        return GeocodeResult(
            latitude=float(value.get("latitude") or 0),
            longitude=float(value.get("longitude") or 0),
            matched_address=str(value.get("matched_address") or ""),
            match_confidence=str(value.get("match_confidence") or ""),
            source=str(value.get("source") or "census_geocoder"),
        )
    return None


def _load_cache(path: Path) -> dict[str, object]:
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


def _write_cache(path: Path, cache: dict[str, object]) -> None:
    tmp_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, sort_keys=True)
    tmp_path.replace(path)
