from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

from marketing_lead.models import LeadCandidate

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
DEFAULT_MATCH_MODEL = "kimi-k2.6:cloud"


def review_customer_match_with_ollama(
    lead: LeadCandidate,
    customer: dict[str, str],
    candidate_reason: str,
    model: str = DEFAULT_MATCH_MODEL,
    timeout_seconds: int = 30,
) -> tuple[bool, int, str] | None:
    prompt = (
        "Compare these two business records and decide if they refer to the same real-world business. "
        "Use only the fields provided. Consider name similarity, exact street address, suite/unit, city, ZIP, "
        "phone, and whether the address may be a shared venue. "
        "Return only JSON with keys: same_business, confidence, reason. "
        "confidence must be 0-100. Set same_business false if the names conflict at the same address.\n\n"
        f"Candidate reason: {candidate_reason}\n\n"
        "Lead record:\n"
        f"Name: {lead.name}\n"
        f"Category: {lead.category}\n"
        f"Address: {lead.address_1}, {lead.city}, {lead.state} {lead.postcode}\n"
        f"Phone: {lead.phone}\n"
        f"Website: {lead.website}\n"
        f"Source: {lead.source}\n\n"
        "Internal customer record:\n"
        f"Customer ID: {customer.get('customer_id', '')}\n"
        f"Business: {customer.get('business', '')}\n"
        f"Address: {customer.get('address1', '')} {customer.get('address2', '')}, "
        f"{customer.get('city', '')}, {customer.get('state', '')} {customer.get('zip', '')}\n"
        f"Phone: {customer.get('phone', '')}\n"
        f"Status: {customer.get('status', '')}\n"
        f"Branch: {customer.get('branch', '')}\n"
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0},
    }
    request = Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))

    content = str(data.get("message", {}).get("content", ""))
    decision = _parse_json_object(content)
    if not decision:
        return None

    same_business = bool(decision.get("same_business"))
    confidence = int(float(decision.get("confidence") or 0))
    reason = " ".join(str(decision.get("reason") or "").split())[:300]
    return same_business, max(0, min(confidence, 100)), reason


def _parse_json_object(content: str) -> dict[str, object] | None:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content, flags=re.IGNORECASE).strip()
        content = re.sub(r"```$", "", content).strip()
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if match:
        content = match.group(0)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
