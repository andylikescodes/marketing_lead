from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from marketing_lead.models import LeadCandidate, ZipLocation

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "marketing-lead-prototype/0.1"

AMENITIES = "restaurant|fast_food|cafe|bar|pub|food_court|ice_cream"
SHOPS = "bakery|deli|butcher|seafood|supermarket|greengrocer|convenience|beverages|alcohol"


def collect_osm_leads(
    location: ZipLocation,
    radius_meters: int,
    overpass_url: str = OVERPASS_URL,
    timeout_seconds: int = 45,
) -> list[LeadCandidate]:
    query = f"""
[out:json][timeout:{min(timeout_seconds, 180)}];
(
  nwr["amenity"~"^({AMENITIES})$"](around:{radius_meters},{location.latitude},{location.longitude});
  nwr["shop"~"^({SHOPS})$"](around:{radius_meters},{location.latitude},{location.longitude});
  nwr["craft"="caterer"](around:{radius_meters},{location.latitude},{location.longitude});
);
out center tags;
"""
    payload = urlencode({"data": query}).encode("utf-8")
    request = Request(
        overpass_url,
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    with urlopen(request, timeout=timeout_seconds + 10) as response:
        data = json.loads(response.read().decode("utf-8"))

    return [_element_to_candidate(element) for element in data.get("elements", []) if element.get("tags")]


def _element_to_candidate(element: dict[str, object]) -> LeadCandidate:
    tags = element.get("tags") or {}
    if not isinstance(tags, dict):
        tags = {}

    lat, lon = _coordinates(element)
    category = _category(tags)
    street = _street_address(tags)

    return LeadCandidate(
        name=str(tags.get("name") or ""),
        category=category,
        address_1=street,
        city=str(tags.get("addr:city") or ""),
        state=str(tags.get("addr:state") or ""),
        postcode=str(tags.get("addr:postcode") or ""),
        latitude=lat,
        longitude=lon,
        phone=str(tags.get("phone") or tags.get("contact:phone") or ""),
        website=str(tags.get("website") or tags.get("contact:website") or ""),
        opening_hours=str(tags.get("opening_hours") or ""),
        source="openstreetmap",
        source_id=f"{element.get('type')}:{element.get('id')}",
    )


def _coordinates(element: dict[str, object]) -> tuple[float, float]:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])

    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])

    raise ValueError(f"OSM element has no usable coordinates: {element.get('type')}:{element.get('id')}")


def _category(tags: dict[object, object]) -> str:
    for key in ("amenity", "shop", "craft", "cuisine"):
        value = tags.get(key)
        if value:
            return f"{key}:{value}"
    return "unknown"


def _street_address(tags: dict[object, object]) -> str:
    house_number = str(tags.get("addr:housenumber") or "").strip()
    street = str(tags.get("addr:street") or "").strip()
    unit = str(tags.get("addr:unit") or "").strip()
    parts = [part for part in [house_number, street] if part]
    address = " ".join(parts)
    if unit:
        address = f"{address} #{unit}" if address else f"#{unit}"
    return address
