from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from marketing_lead.models import LeadCandidate, ZipLocation

OPEN_BREWERY_URL = "https://api.openbrewerydb.org/v1/breweries"


def collect_openbrewery_leads(
    location: ZipLocation,
    *,
    radius_meters: int,
    per_page: int = 200,
    timeout_seconds: int = 30,
) -> list[LeadCandidate]:
    """Collect nearby brewery/taproom leads from Open Brewery DB.

    Open Brewery DB supports a by_dist lookup around coordinates but does not
    provide a radius filter, so we collect a bounded page and apply our own
    distance threshold.
    """
    params = {
        "by_dist": f"{location.latitude:.6f},{location.longitude:.6f}",
        "per_page": max(1, min(per_page, 200)),
    }
    url = f"{OPEN_BREWERY_URL}?{urlencode(params)}"
    with urlopen(url, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    leads: list[LeadCandidate] = []
    for item in payload:
        lat = _to_float(item.get("latitude"))
        lon = _to_float(item.get("longitude"))
        if lat is None or lon is None:
            continue
        if _distance_meters(location.latitude, location.longitude, lat, lon) > radius_meters:
            continue

        name = str(item.get("name") or "").strip()
        if not name:
            continue

        leads.append(
            LeadCandidate(
                name=name,
                category=_brewery_category(str(item.get("brewery_type") or "")),
                latitude=lat,
                longitude=lon,
                source="openbrewerydb",
                source_id=str(item.get("id") or ""),
                address_1=str(item.get("street") or ""),
                city=str(item.get("city") or ""),
                state=str(item.get("state") or ""),
                postcode=str(item.get("postal_code") or ""),
                phone=str(item.get("phone") or ""),
                website=str(item.get("website_url") or ""),
            )
        )
    return leads


def _brewery_category(brewery_type: str) -> str:
    normalized = brewery_type.strip().lower()
    if normalized in {"brewpub", "taproom", "micro"}:
        return "bar"
    return "brewery"


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Equirectangular approximation (good for short distances).
    from math import cos, radians, sqrt

    x = radians(lon2 - lon1) * cos(radians((lat1 + lat2) / 2))
    y = radians(lat2 - lat1)
    return 6371000 * sqrt(x * x + y * y)
