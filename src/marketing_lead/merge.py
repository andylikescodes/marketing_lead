from __future__ import annotations

import re
from difflib import SequenceMatcher

from marketing_lead.models import LeadCandidate


def merge_leads(leads: list[LeadCandidate]) -> list[LeadCandidate]:
    merged: list[LeadCandidate] = []
    for lead in leads:
        match = _find_match(merged, lead)
        if match:
            _merge_into(match, lead)
        else:
            merged.append(lead)
    return merged


def _find_match(existing: list[LeadCandidate], incoming: LeadCandidate) -> LeadCandidate | None:
    incoming_address = _normalize_address(incoming.address_1)
    incoming_name = _normalize_name(incoming.name)
    for candidate in existing:
        same_postcode = bool(candidate.postcode and incoming.postcode and candidate.postcode == incoming.postcode)
        same_address = incoming_address and incoming_address == _normalize_address(candidate.address_1)
        if same_postcode and same_address:
            return candidate

        candidate_name = _normalize_name(candidate.name)
        if same_postcode and incoming_name and candidate_name:
            ratio = SequenceMatcher(None, incoming_name, candidate_name).ratio()
            if ratio >= 0.88:
                return candidate

        if _close_coordinates(candidate, incoming) and incoming_name and candidate_name:
            ratio = SequenceMatcher(None, incoming_name, candidate_name).ratio()
            if ratio >= 0.82:
                return candidate
    return None


def _merge_into(target: LeadCandidate, incoming: LeadCandidate) -> None:
    target.source = _append_unique(target.source, incoming.source)
    target.source_id = _append_unique(target.source_id, incoming.source_id)

    for field_name in [
        "name",
        "category",
        "address_1",
        "city",
        "state",
        "postcode",
        "phone",
        "website",
        "opening_hours",
    ]:
        current = getattr(target, field_name)
        new_value = getattr(incoming, field_name)
        if not current and new_value:
            setattr(target, field_name, new_value)

    if _has_better_coordinates(incoming, target):
        target.latitude = incoming.latitude
        target.longitude = incoming.longitude

    target.signals = _merge_list(target.signals, incoming.signals)
    target.warnings = _merge_list(target.warnings, incoming.warnings)
    if len(set(target.source_names)) > 1 and "validated_by_multiple_free_sources" not in target.signals:
        target.signals.append("validated_by_multiple_free_sources")
        target.warnings = [warning for warning in target.warnings if warning != "single_source_only"]
    if "openstreetmap" in target.source_names or "address_geocoded_by_census" in target.signals:
        target.warnings = [warning for warning in target.warnings if warning != "using_zip_centroid_coordinates"]


def _append_unique(existing: str, incoming: str) -> str:
    values = []
    for value in [*existing.split(";"), *incoming.split(";")]:
        stripped = value.strip()
        if stripped and stripped not in values:
            values.append(stripped)
    return "; ".join(values)


def _merge_list(first: list[str], second: list[str]) -> list[str]:
    values = list(first)
    for value in second:
        if value not in values:
            values.append(value)
    return values


def _normalize_name(value: str) -> str:
    value = value.lower()
    value = re.sub(r"&", " and ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    for suffix in [" inc ", " llc ", " corp ", " corporation ", " co ", " ltd "]:
        value = value.replace(suffix, " ")
    return " ".join(value.split())


def _normalize_address(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9#]+", " ", value)
    replacements = {
        " street ": " st ",
        " avenue ": " ave ",
        " boulevard ": " blvd ",
        " road ": " rd ",
        " drive ": " dr ",
        " suite ": " ste ",
    }
    value = f" {value} "
    for before, after in replacements.items():
        value = value.replace(before, after)
    return " ".join(value.split())


def _close_coordinates(first: LeadCandidate, second: LeadCandidate) -> bool:
    return abs(first.latitude - second.latitude) <= 0.0007 and abs(first.longitude - second.longitude) <= 0.0007


def _has_better_coordinates(incoming: LeadCandidate, target: LeadCandidate) -> bool:
    incoming_is_precise = "using_zip_centroid_coordinates" not in incoming.warnings
    target_is_precise = "using_zip_centroid_coordinates" not in target.warnings
    return incoming_is_precise and not target_is_precise
