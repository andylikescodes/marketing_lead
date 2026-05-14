from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ZipLocation:
    zip_code: str
    latitude: float
    longitude: float
    source: str


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
        }
