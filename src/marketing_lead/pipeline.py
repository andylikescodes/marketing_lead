from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from marketing_lead.ca_abc import collect_ca_abc_leads
from marketing_lead.customer_snapshot import DEFAULT_SNAPSHOT_PATH, apply_customer_matches
from marketing_lead.llm import annotate_with_llm
from marketing_lead.merge import merge_leads
from marketing_lead.openbrewery import collect_openbrewery_leads
from marketing_lead.models import LeadCandidate, ZipLocation
from marketing_lead.osm import OVERPASS_URL, collect_osm_leads
from marketing_lead.scoring import score_leads
from marketing_lead.zcta import lookup_zip_centroid

METERS_PER_MILE = 1609.344
ProgressCallback = Callable[[dict[str, object]], None]


@dataclass
class SourceReport:
    name: str
    label: str
    count: int
    status: str
    detail: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SourceReport":
        return cls(
            name=str(payload.get("name") or ""),
            label=str(payload.get("label") or ""),
            count=int(payload.get("count") or 0),
            status=str(payload.get("status") or ""),
            detail=str(payload.get("detail") or ""),
        )


@dataclass
class LeadSearchResult:
    zip_code: str
    radius_mi: float
    location: ZipLocation
    source_reports: list[SourceReport]
    leads: list[LeadCandidate]
    merged_count: int

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "LeadSearchResult":
        zip_code = str(payload.get("zip_code") or "")
        location_payload = payload.get("location") or {}
        if not isinstance(location_payload, dict):
            location_payload = {}
        summary = payload.get("summary") or {}
        merged_count = payload.get("merged_count") or 0
        if isinstance(summary, dict):
            merged_count = summary.get("merged_count") or merged_count
        return cls(
            zip_code=zip_code,
            radius_mi=float(payload.get("radius_mi") or 0),
            location=ZipLocation.from_dict(location_payload, zip_code=zip_code),
            source_reports=[
                SourceReport.from_dict(report)
                for report in payload.get("source_reports", [])
                if isinstance(report, dict)
            ],
            leads=[
                LeadCandidate.from_dict(lead)
                for lead in payload.get("leads", [])
                if isinstance(lead, dict)
            ],
            merged_count=int(merged_count),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "zip_code": self.zip_code,
            "radius_mi": self.radius_mi,
            "location": {
                "latitude": self.location.latitude,
                "longitude": self.location.longitude,
                "source": self.location.source,
            },
            "source_reports": [report.__dict__ for report in self.source_reports],
            "summary": {
                "lead_count": len(self.leads),
                "merged_count": self.merged_count,
                "multi_source_count": sum(1 for lead in self.leads if len(set(lead.source_names)) > 1),
                "high_score_count": sum(1 for lead in self.leads if lead.confidence_score >= 80),
                "review_first_count": sum(1 for lead in self.leads if 65 <= lead.confidence_score < 80),
                "existing_customer_count": sum(1 for lead in self.leads if lead.lead_status == "existing_customer"),
            },
            "leads": [lead.as_dict() for lead in self.leads],
        }


def search_leads(
    zip_code: str,
    radius_mi: float = 1.0,
    include_abc: bool = True,
    include_llm: bool = False,
    llm_model: str = "kimi-k2.6:cloud",
    llm_limit: int = 0,
    limit: int = 0,
    overpass_url: str = OVERPASS_URL,
    overpass_timeout: int = 45,
    include_customer_snapshot: bool = True,
    customer_snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
    progress_callback: ProgressCallback | None = None,
) -> LeadSearchResult:
    _progress(progress_callback, 3, "Resolving ZIP/ZCTA center.", stage="zip")
    location = lookup_zip_centroid(zip_code)
    _progress(
        progress_callback,
        8,
        f"ZIP {location.zip_code} resolved to {location.latitude:.5f}, {location.longitude:.5f}.",
        stage="zip",
    )
    radius_meters = max(1, int(radius_mi * METERS_PER_MILE))
    all_leads: list[LeadCandidate] = []
    reports: list[SourceReport] = []

    _progress(progress_callback, 12, "Searching OpenStreetMap / Overpass.", stage="openstreetmap")
    try:
        osm_leads = collect_osm_leads(
            location,
            radius_meters,
            overpass_url=overpass_url,
            timeout_seconds=overpass_timeout,
        )
        all_leads.extend(osm_leads)
        reports.append(
            SourceReport(
                name="openstreetmap",
                label="OpenStreetMap / Overpass",
                count=len(osm_leads),
                status="ok",
                detail="Free POI discovery for restaurants, cafes, bars, bakeries, grocery, and related food businesses.",
            )
        )
    except Exception as exc:
        reports.append(
            SourceReport(
                name="openstreetmap",
                label="OpenStreetMap / Overpass",
                count=0,
                status="error",
                detail=str(exc),
            )
        )


    _progress(progress_callback, 24, "Searching Open Brewery DB.", stage="openbrewery")
    try:
        openbrewery_leads = collect_openbrewery_leads(
            location,
            radius_meters=radius_meters,
        )
        all_leads.extend(openbrewery_leads)
        reports.append(
            SourceReport(
                name="openbrewerydb",
                label="Open Brewery DB",
                count=len(openbrewery_leads),
                status="ok",
                detail="Free brewery/taproom directory source used as an independent cross-check for alcohol-serving leads.",
            )
        )
    except Exception as exc:
        reports.append(
            SourceReport(
                name="openbrewerydb",
                label="Open Brewery DB",
                count=0,
                status="error",
                detail=str(exc),
            )
        )

    if include_abc:
        _progress(progress_callback, 34, "Checking California ABC license data.", stage="ca_abc")
        try:
            abc_leads = collect_ca_abc_leads(location)
            all_leads.extend(abc_leads)
            reports.append(
                SourceReport(
                    name="ca_abc",
                    label="California ABC Daily License Export",
                    count=len(abc_leads),
                    status="ok",
                    detail="Free California alcohol license/application data; useful for restaurants, bars, groceries, liquor stores, and brewpubs.",
                )
            )
        except Exception as exc:
            reports.append(
                SourceReport(
                    name="ca_abc",
                    label="California ABC Daily License Export",
                    count=0,
                    status="error",
                    detail=str(exc),
                )
            )

    _progress(progress_callback, 48, "Merging duplicate source records.", stage="merge")
    merged = merge_leads(all_leads)

    if include_customer_snapshot:
        _progress(progress_callback, 58, "Matching against local customer snapshot.", stage="customer_snapshot")
        customer_status = "ok"
        customer_count, customer_detail = apply_customer_matches(merged, snapshot_path=customer_snapshot_path)
        if "not found" in customer_detail.lower():
            customer_status = "warning"
        reports.append(
            SourceReport(
                name="customer_snapshot",
                label="Internal Customer Snapshot",
                count=customer_count,
                status=customer_status,
                detail=customer_detail,
            )
        )
    else:
        _progress(
            progress_callback,
            58,
            "Skipping local customer snapshot; discovery artifact is cloud-portable.",
            stage="customer_snapshot",
        )

    _progress(progress_callback, 68, "Scoring source and customer signals.", stage="scoring")
    scored = score_leads(merged)
    if limit:
        scored = scored[:limit]

    if include_llm:
        _progress(progress_callback, 76, "Running Ollama web verification and lead notes.", stage="llm")
        annotate_with_llm(
            scored,
            model=llm_model,
            limit=llm_limit,
            progress_callback=progress_callback,
        )
        _progress(progress_callback, 94, "Rescoring leads after LLM review.", stage="scoring")
        scored = score_leads(scored)

    _progress(progress_callback, 100, f"Search complete with {len(scored)} leads.", stage="complete")
    return LeadSearchResult(
        zip_code=location.zip_code,
        radius_mi=radius_mi,
        location=location,
        source_reports=reports,
        leads=scored,
        merged_count=max(0, len(all_leads) - len(merged)),
    )


def _progress(
    callback: ProgressCallback | None,
    percent: int,
    message: str,
    stage: str,
    **extra: object,
) -> None:
    if callback:
        payload: dict[str, object] = {"progress": percent, "message": message, "stage": stage}
        payload.update(extra)
        callback(payload)
