from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from marketing_lead.customer_snapshot import PROJECT_ROOT
from marketing_lead.models import LeadCandidate

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_WEB_SEARCH_URL = "https://ollama.com/api/web_search"
OLLAMA_WEB_FETCH_URL = "https://ollama.com/api/web_fetch"
DEFAULT_MODEL = "kimi-k2.6:cloud"
DEFAULT_WEB_CACHE_PATH = PROJECT_ROOT / "data" / "ollama_web_cache.sqlite"

ProgressCallback = Callable[[dict[str, object]], None]


def annotate_with_llm(
    leads: list[LeadCandidate],
    model: str = DEFAULT_MODEL,
    limit: int = 0,
    timeout_seconds: int = 45,
    use_web_search: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> None:
    selected = leads if limit <= 0 else leads[:limit]
    total = len(selected)
    for index, lead in enumerate(selected, start=1):
        if progress_callback:
            progress_callback(
                {
                    "stage": "llm",
                    "message": f"Reviewing lead {index} of {total}: {lead.name or 'Unnamed lead'}",
                    "current_lead": lead.name,
                    "review_index": index,
                    "review_total": total,
                }
            )
        evidence = _collect_web_evidence(lead, timeout_seconds=timeout_seconds) if use_web_search else []
        lead.llm_notes = _classify_lead(
            lead,
            model=model,
            web_evidence=evidence,
            timeout_seconds=timeout_seconds,
        )
        if lead.llm_notes and "unavailable" not in lead.llm_notes.lower():
            _append_unique(lead.signals, "llm_reviewed")
        if evidence:
            _append_unique(lead.signals, "web_search_reviewed")
            lead.verification_summary = _join_summary(lead.verification_summary, lead.llm_notes)


def _classify_lead(
    lead: LeadCandidate,
    model: str,
    web_evidence: list[dict[str, str]],
    timeout_seconds: int,
) -> str:
    evidence_lines = []
    for item in web_evidence[:5]:
        title = item.get("title", "")
        url = item.get("url", "")
        content = item.get("content", "")
        evidence_lines.append(f"- {title} ({url}): {content[:700]}")
    evidence_text = "\n".join(evidence_lines) if evidence_lines else "No web evidence was available."

    prompt = (
        "You are reviewing a potential Restaurant Depot lead. "
        "Use only the fields and web evidence provided. Do not invent facts. "
        "Return one concise sentence that says whether this appears to be a restaurant, bar, grocery, "
        "foodservice business, existing customer, or uncertain, and mention the strongest evidence.\n\n"
        f"Name: {lead.name}\n"
        f"Category: {lead.category}\n"
        f"Address: {lead.address_1}, {lead.city}, {lead.state} {lead.postcode}\n"
        f"Phone: {lead.phone}\n"
        f"Website: {lead.website}\n"
        f"Sources: {lead.source}\n"
        f"Signals: {', '.join(lead.signals)}\n"
        f"Warnings: {', '.join(lead.warnings)}\n"
        f"Customer status: {lead.lead_status}; {lead.customer_id}; {lead.customer_status}\n"
        f"Web evidence:\n{evidence_text}\n"
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
        _append_unique(lead.warnings, "llm_unavailable")
        return f"LLM unavailable: {exc.__class__.__name__}"

    content = data.get("message", {}).get("content", "")
    return " ".join(str(content).split())[:500]


def _collect_web_evidence(lead: LeadCandidate, timeout_seconds: int) -> list[dict[str, str]]:
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if not api_key:
        _append_unique(lead.warnings, "ollama_web_search_key_missing")
        return []

    query = _search_query(lead)
    try:
        search_payload = _cached_ollama_api(
            "web_search",
            OLLAMA_WEB_SEARCH_URL,
            {"query": query, "max_results": 5},
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        _append_unique(lead.warnings, "ollama_web_search_failed")
        return []

    raw_results = search_payload.get("results", [])
    if not isinstance(raw_results, list):
        return []

    evidence: list[dict[str, str]] = []
    for result in raw_results[:5]:
        if not isinstance(result, dict):
            continue
        title = str(result.get("title") or "")
        url = str(result.get("url") or "")
        content = " ".join(str(result.get("content") or "").split())
        if url:
            _append_unique(lead.verification_sources, url)
        evidence.append({"title": title, "url": url, "content": content})

    for item in evidence[:2]:
        url = item.get("url", "")
        if not url:
            continue
        try:
            fetch_payload = _cached_ollama_api(
                "web_fetch",
                OLLAMA_WEB_FETCH_URL,
                {"url": url},
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
        except Exception:
            continue
        fetched_content = " ".join(str(fetch_payload.get("content") or "").split())
        if fetched_content:
            item["content"] = fetched_content[:1800]
        fetched_title = str(fetch_payload.get("title") or "")
        if fetched_title:
            item["title"] = fetched_title

    return evidence


def _cached_ollama_api(
    namespace: str,
    url: str,
    payload: dict[str, object],
    api_key: str,
    timeout_seconds: int,
) -> dict[str, object]:
    DEFAULT_WEB_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache_key = _cache_key(namespace, payload)
    connection = sqlite3.connect(DEFAULT_WEB_CACHE_PATH)
    try:
        _ensure_cache_schema(connection)
        row = connection.execute("SELECT payload FROM cache WHERE cache_key = ?", (cache_key,)).fetchone()
        if row:
            return json.loads(row[0])

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))

        connection.execute(
            """
            INSERT OR REPLACE INTO cache (cache_key, namespace, created_at, payload)
            VALUES (?, ?, ?, ?)
            """,
            (cache_key, namespace, int(time.time()), json.dumps(data)),
        )
        connection.commit()
        return data
    finally:
        connection.close()


def _ensure_cache_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            cache_key TEXT PRIMARY KEY,
            namespace TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )


def _cache_key(namespace: str, payload: dict[str, object]) -> str:
    raw = json.dumps({"namespace": namespace, "payload": payload}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _search_query(lead: LeadCandidate) -> str:
    parts = [lead.name, lead.address_1, lead.city, lead.state, lead.postcode, lead.phone]
    return " ".join(part for part in parts if part).strip()


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _join_summary(existing: str, addition: str) -> str:
    if not addition:
        return existing
    if not existing:
        return addition
    return f"{existing} {addition}"
