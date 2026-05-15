from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from marketing_lead.zcta import USER_AGENT


@dataclass(frozen=True)
class SocrataDataset:
    base_url: str
    dataset_id: str
    app_token: str = ""


def fetch_rows(dataset: SocrataDataset, *, limit: int = 500, where: str = "", select: str = "*", timeout_seconds: int = 20) -> list[dict[str, Any]]:
    params: dict[str, str | int] = {"$limit": max(1, min(limit, 50000)), "$select": select}
    if where:
        params["$where"] = where
    query = urlencode(params)
    url = f"{dataset.base_url.rstrip('/')}/resource/{dataset.dataset_id}.json?{query}"
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if dataset.app_token:
        headers["X-App-Token"] = dataset.app_token
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]
