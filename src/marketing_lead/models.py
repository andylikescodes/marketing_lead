from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ZipLocation:
    zip_code: str
    latitude: float
    longitude: float
    source: str

    @classmethod
    def from_dict(cls, payload: dict[str, object], zip_code: str = "") -> "ZipLocation":
        return cls(
            zip_code=str(payload.get("zip_code") or zip_code),
            latitude=float(payload.get("latitude") or 0),
            longitude=float(payload.get("longitude") or 0),
            source=str(payload.get("source") or ""),
        )


@dataclass
class LeadCandidate:
    name: str
    category: str
    latitude: float
    longitude: float
    source: str
    source_id: str
    address_1: str = ""
    city: str = ""
    state: str = ""
    postcode: str = ""
    phone: str = ""
    website: str = ""
    opening_hours: str = ""
    confidence_score: int = 0
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    llm_notes: str = ""
    lead_status: str = "new_lead"
    customer_id: str = ""
    customer_status: str = ""
    customer_branch: str = ""
    customer_last_visit: str = ""
    customer_last_shopped: str = ""
    customer_match_confidence: int = 0
    verification_summary: str = ""
    verification_sources: list[str] = field(default_factory=list)
    geocode_source: str = ""
    geocode_confidence: str = ""
    geocode_matched_address: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "LeadCandidate":
        return cls(
            name=str(payload.get("name") or ""),
            category=str(payload.get("category") or "unknown"),
            address_1=str(payload.get("address_1") or ""),
            city=str(payload.get("city") or ""),
            state=str(payload.get("state") or ""),
            postcode=str(payload.get("postcode") or ""),
            latitude=float(payload.get("latitude") or 0),
            longitude=float(payload.get("longitude") or 0),
            phone=str(payload.get("phone") or ""),
            website=str(payload.get("website") or ""),
            opening_hours=str(payload.get("opening_hours") or ""),
            source=str(payload.get("source") or ""),
            source_id=str(payload.get("source_id") or ""),
            confidence_score=int(payload.get("confidence_score") or 0),
            signals=_split_list(payload.get("signals")),
            warnings=_split_list(payload.get("warnings")),
            llm_notes=str(payload.get("llm_notes") or ""),
            lead_status=str(payload.get("lead_status") or "new_lead"),
            customer_id=str(payload.get("customer_id") or ""),
            customer_status=str(payload.get("customer_status") or ""),
            customer_branch=str(payload.get("customer_branch") or ""),
            customer_last_visit=str(payload.get("customer_last_visit") or ""),
            customer_last_shopped=str(payload.get("customer_last_shopped") or ""),
            customer_match_confidence=int(payload.get("customer_match_confidence") or 0),
            verification_summary=str(payload.get("verification_summary") or ""),
            verification_sources=_split_list(payload.get("verification_sources")),
            geocode_source=str(payload.get("geocode_source") or ""),
            geocode_confidence=str(payload.get("geocode_confidence") or ""),
            geocode_matched_address=str(payload.get("geocode_matched_address") or ""),
        )

    @property
    def source_names(self) -> list[str]:
        return [part.strip() for part in self.source.split(";") if part.strip()]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "category": self.category,
            "address_1": self.address_1,
            "city": self.city,
            "state": self.state,
            "postcode": self.postcode,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "phone": self.phone,
            "website": self.website,
            "opening_hours": self.opening_hours,
            "source": self.source,
            "source_count": len(set(self.source_names)),
            "source_id": self.source_id,
            "confidence_score": self.confidence_score,
            "signals": "; ".join(self.signals),
            "warnings": "; ".join(self.warnings),
            "llm_notes": self.llm_notes,
            "lead_status": self.lead_status,
            "customer_id": self.customer_id,
            "customer_status": self.customer_status,
            "customer_branch": self.customer_branch,
            "customer_last_visit": self.customer_last_visit,
            "customer_last_shopped": self.customer_last_shopped,
            "customer_match_confidence": self.customer_match_confidence,
            "verification_summary": self.verification_summary,
            "verification_sources": "; ".join(self.verification_sources),
            "geocode_source": self.geocode_source,
            "geocode_confidence": self.geocode_confidence,
            "geocode_matched_address": self.geocode_matched_address,
        }


def _split_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(";") if part.strip()]
