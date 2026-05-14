from __future__ import annotations

import csv
import io
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from marketing_lead.geocode import geocode_address
from marketing_lead.models import LeadCandidate, ZipLocation
from marketing_lead.zcta import USER_AGENT, default_cache_dir

ABC_DAILY_CSV_ZIP_URL = "https://www.abc.ca.gov/wp-content/uploads/DailyExport-CSV.zip"
CACHE_MAX_AGE_SECONDS = 18 * 60 * 60

ABC_RELEVANT_TYPES = {
    "20": "off-sale beer/wine retail",
    "21": "off-sale general retail",
    "23": "small beer manufacturer",
    "40": "bar/tavern beer",
    "41": "restaurant beer/wine eating place",
    "42": "bar/tavern beer/wine",
    "47": "restaurant general eating place",
    "48": "bar/nightclub general",
    "49": "seasonal restaurant general",
    "59": "seasonal restaurant beer/wine",
    "75": "brewpub restaurant",
}


def collect_ca_abc_leads(
    location: ZipLocation,
    geocode: bool = False,
    max_geocodes: int = 0,
    cache_dir: Path | None = None,
) -> list[LeadCandidate]:
    if not _looks_like_california_zip(location.zip_code):
        return []

    csv_path = _get_abc_csv(cache_dir or default_cache_dir())
    leads: list[LeadCandidate] = []
    geocode_count = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        fh.readline()  # First row is an "Updated ..." metadata line.
        reader = csv.DictReader(fh)
        for raw_row in reader:
            row = {_clean_header(key): (value or "").strip() for key, value in raw_row.items()}
            if _zip5(row.get("Prem Zip", "")) != location.zip_code:
                continue

            license_type = row.get("License Type", "").zfill(2)
            if license_type not in ABC_RELEVANT_TYPES:
                continue

            type_status = row.get("Type Status", "").upper()
            lic_or_app = row.get("Lic or App", "").upper()
            if type_status != "ACTIVE" or lic_or_app not in {"LIC", "APP"}:
                continue

            address = _join_address(row.get("Prem Addr 1", ""), row.get("Prem Addr 2", ""))
            city = row.get("Prem City", "")
            state = row.get("Prem State", "")
            postcode = _zip5(row.get("Prem Zip", "")) or row.get("Prem Zip", "")
            full_address = ", ".join(part for part in [address, city, state, postcode] if part)

            lat = location.latitude
            lon = location.longitude
            warnings: list[str] = []
            signals = [
                "ca_abc_active_license" if lic_or_app == "LIC" else "ca_abc_active_application",
                f"abc_type_{license_type}",
            ]

            if lic_or_app == "APP":
                warnings.append("abc_application_not_issued_license")

            if geocode and full_address and geocode_count < max_geocodes:
                geocode_count += 1
                coordinates = geocode_address(full_address, cache_dir=cache_dir)
                if coordinates:
                    lat, lon = coordinates
                    signals.append("address_geocoded_by_census")
                else:
                    warnings.append("using_zip_centroid_coordinates")
            else:
                warnings.append("using_zip_centroid_coordinates")

            dba_name = row.get("DBA Name", "")
            primary_name = row.get("Primary Name", "")
            name = dba_name or primary_name

            leads.append(
                LeadCandidate(
                    name=name,
                    category=f"ca_abc:{ABC_RELEVANT_TYPES[license_type]}",
                    address_1=address,
                    city=city.title() if city else "",
                    state=state,
                    postcode=postcode,
                    latitude=lat,
                    longitude=lon,
                    source="ca_abc",
                    source_id=f"{license_type}:{row.get('File Number', '')}:{lic_or_app}",
                    signals=signals,
                    warnings=warnings,
                )
            )

    return leads


def _get_abc_csv(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    csv_path = cache_dir / "ABC-DailyDataExport.csv"
    if csv_path.exists() and time.time() - csv_path.stat().st_mtime < CACHE_MAX_AGE_SECONDS:
        return csv_path

    request = Request(ABC_DAILY_CSV_ZIP_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        payload = response.read()

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError("Unexpected California ABC export archive layout.")
        csv_path.write_bytes(archive.read(members[0]))

    return csv_path


def _clean_header(value: str | None) -> str:
    return (value or "").replace("\ufeff", "").strip()


def _zip5(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:5]


def _join_address(line1: str, line2: str) -> str:
    line1 = " ".join(line1.split())
    line2 = " ".join(line2.split())
    return ", ".join(part for part in [line1, line2] if part)


def _looks_like_california_zip(zip_code: str) -> bool:
    try:
        value = int(zip_code)
    except ValueError:
        return False
    return 90001 <= value <= 96162
