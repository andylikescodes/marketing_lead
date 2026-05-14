from __future__ import annotations

import json
from pathlib import Path

from marketing_lead.pipeline import LeadSearchResult

DISCOVERY_BUNDLE_TYPE = "marketing_lead.discovery_bundle"
DISCOVERY_BUNDLE_VERSION = 1


def write_discovery_bundle(
    output_path: Path,
    result: LeadSearchResult,
    parameters: dict[str, object],
    run_log: list[dict[str, object]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_type": DISCOVERY_BUNDLE_TYPE,
        "version": DISCOVERY_BUNDLE_VERSION,
        "parameters": parameters,
        "run_log": run_log,
        "result": result.as_dict(),
    }
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def read_discovery_bundle(input_path: Path) -> tuple[LeadSearchResult, dict[str, object], list[dict[str, object]]]:
    with input_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if payload.get("artifact_type") != DISCOVERY_BUNDLE_TYPE:
        raise ValueError(f"Unsupported artifact type: {payload.get('artifact_type')!r}")
    if int(payload.get("version") or 0) != DISCOVERY_BUNDLE_VERSION:
        raise ValueError(f"Unsupported discovery bundle version: {payload.get('version')!r}")

    result_payload = payload.get("result") or {}
    if not isinstance(result_payload, dict):
        raise ValueError("Discovery bundle is missing a valid result payload.")

    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, dict):
        parameters = {}

    run_log = payload.get("run_log") or []
    if not isinstance(run_log, list):
        run_log = []

    return LeadSearchResult.from_dict(result_payload), parameters, [
        event for event in run_log if isinstance(event, dict)
    ]
