from __future__ import annotations

import json
from urllib.request import Request, urlopen

from marketing_lead.models import LeadCandidate

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "kimi-k2.6:cloud"


def annotate_with_llm(
    leads: list[LeadCandidate],
    model: str = DEFAULT_MODEL,
    limit: int = 20,
    timeout_seconds: int = 45,
) -> None:
    for lead in leads[: max(0, limit)]:
        lead.llm_notes = _classify_lead(lead, model=model, timeout_seconds=timeout_seconds)
        if lead.llm_notes:
            lead.signals.append("llm_reviewed")


def _classify_lead(lead: LeadCandidate, model: str, timeout_seconds: int) -> str:
    prompt = (
        "You are reviewing a potential Restaurant Depot lead. "
        "Use only the fields provided. Do not invent facts. "
        "Return one short sentence: classify as restaurant, bar, grocery, foodservice, or uncertain, "
        "and mention the strongest reason.\n\n"
        f"Name: {lead.name}\n"
        f"Category: {lead.category}\n"
        f"Address: {lead.address_1}, {lead.city}, {lead.state} {lead.postcode}\n"
        f"Sources: {lead.source}\n"
        f"Signals: {', '.join(lead.signals)}\n"
        f"Warnings: {', '.join(lead.warnings)}\n"
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.1},
    }
    request = Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return f"LLM unavailable: {exc.__class__.__name__}"

    content = data.get("message", {}).get("content", "")
    return " ".join(str(content).split())[:240]
