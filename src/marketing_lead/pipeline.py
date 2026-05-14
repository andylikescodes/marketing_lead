from __future__ import annotations

from dataclasses import dataclass

from marketing_lead.ca_abc import collect_ca_abc_leads
from marketing_lead.llm import annotate_with_llm
from marketing_lead.merge import merge_leads
from marketing_lead.models import LeadCandidate, ZipLocation
from marketing_lead.osm import OVERPASS_URL, collect_osm_leads
from marketing_lead.scoring import score_leads
from marketing_lead.zcta import lookup_zip_centroid

METERS_PER_MILE = 1609.344


@dataclass
class SourceReport:
    name: str
    label: str
    count: int
    status: str
    detail: str = ""


@dataclass
class LeadSearchResult:
    zip_code: str
    radius_mi: float
    location: ZipLocation
    source_reports: list[SourceReport]
    leads: list[LeadCandidate]
    merged_count: int

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
            },
            "leads": [lead.as_dict() for lead in self.leads],
        }


def search_leads(
    zip_code: str,
    radius_mi: float = 1.0,
    include_abc: bool = True,
    include_llm: bool = False,
    llm_model: str = "kimi-k2.6:cloud",
    llm_limit: int = 15,
    limit: int = 0,
    overpass_url: str = OVERPASS_URL,
    overpass_timeout: int = 45,
) -> LeadSearchResult:
    location = lookup_zip_centroid(zip_code)
    radius_meters = max(1, int(radius_mi * METERS_PER_MILE))
    all_leads: list[LeadCandidate] = []
    reports: list[SourceReport] = []

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

    if include_abc:
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

    merged = merge_leads(all_leads)
    scored = score_leads(merged)
    if limit:
        scored = scored[:limit]

    if include_llm:
        annotate_with_llm(scored, model=llm_model, limit=llm_limit)
        scored = score_leads(scored)

    return LeadSearchResult(
        zip_code=location.zip_code,
        radius_mi=radius_mi,
        location=location,
        source_reports=reports,
        leads=scored,
        merged_count=max(0, len(all_leads) - len(merged)),
    )
