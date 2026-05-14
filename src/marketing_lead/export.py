from __future__ import annotations

import csv
import json
from pathlib import Path

from marketing_lead.models import LeadCandidate

CSV_FIELDS = [
    "name",
    "category",
    "address_1",
    "city",
    "state",
    "postcode",
    "latitude",
    "longitude",
    "phone",
    "website",
    "opening_hours",
    "source",
    "source_count",
    "source_id",
    "confidence_score",
    "signals",
    "warnings",
    "llm_notes",
]


def write_leads(leads: list[LeadCandidate], output_path: Path, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        _write_csv(leads, output_path)
    elif output_format == "json":
        _write_json(leads, output_path)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def _write_csv(leads: list[LeadCandidate], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead.as_dict())


def _write_json(leads: list[LeadCandidate], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump([lead.as_dict() for lead in leads], fh, indent=2)
        fh.write("\n")
