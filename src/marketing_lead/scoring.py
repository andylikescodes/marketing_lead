from __future__ import annotations

from marketing_lead.models import LeadCandidate


def score_leads(leads: list[LeadCandidate]) -> list[LeadCandidate]:
    for lead in leads:
        score_lead(lead)
    return sorted(leads, key=lambda item: (-item.confidence_score, item.name.lower()))


def score_lead(lead: LeadCandidate) -> LeadCandidate:
    lead.signals = _dedupe(lead.signals)
    lead.warnings = _dedupe(lead.warnings)
    score = 25

    if lead.name:
        score += 15
        lead.signals.append("has_name")
    else:
        lead.warnings.append("missing_name")

    if lead.address_1 and lead.city and lead.state:
        score += 18
        lead.signals.append("has_full_address")
    elif lead.address_1:
        score += 10
        lead.signals.append("has_partial_address")
    else:
        score -= 20
        lead.warnings.append("missing_street_address")

    if lead.phone:
        score += 10
        lead.signals.append("has_phone")

    if lead.website:
        score += 10
        lead.signals.append("has_website")

    if lead.opening_hours:
        score += 8
        lead.signals.append("has_opening_hours")

    if lead.category != "unknown":
        score += 7
        lead.signals.append("has_foodservice_category")

    source_count = len(set(lead.source_names))
    if source_count >= 2:
        score += 18
        lead.signals.append("validated_by_multiple_free_sources")
        lead.warnings = [
            warning
            for warning in lead.warnings
            if warning not in {"single_source_only", "single_source_osm_only"}
        ]
    else:
        lead.warnings.append("single_source_only")

    if "ca_abc_active_license" in lead.signals:
        score += 16
        lead.signals.append("validated_active_ca_abc_license")

    if "ca_abc_active_application" in lead.signals:
        score += 6
        lead.signals.append("ca_abc_pending_or_application_signal")

    if "address_geocoded_by_census" in lead.signals:
        score += 5

    if "disused" in lead.category or "abandoned" in lead.category:
        score -= 30
        lead.warnings.append("possibly_closed_or_inactive")

    if lead.llm_notes and "unavailable" not in lead.llm_notes.lower():
        score += 3
        lead.signals.append("llm_reviewed")

    if lead.verification_summary:
        score += 3

    if lead.verification_sources:
        lead.signals.append("has_verification_notes")

    if lead.customer_id or lead.lead_status == "existing_customer":
        lead.lead_status = "existing_customer"
        lead.signals.append("matched_internal_customer")
        lead.warnings.append("existing_customer_not_new_lead")

    # One-source discovery leads should not be treated as dispatch-ready.
    if source_count == 1 and "openstreetmap" in lead.source_names:
        score = min(score, 69)
        lead.warnings.append("single_source_osm_only")
    elif source_count == 1:
        score = min(score, 78)
    else:
        score = min(score, 92)

    if lead.lead_status == "existing_customer":
        score = min(score, 60)

    lead.signals = _dedupe(lead.signals)
    lead.warnings = _dedupe(lead.warnings)
    lead.confidence_score = max(0, min(score, 100))
    return lead


def _dedupe(values: list[str]) -> list[str]:
    deduped = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
