from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from marketing_lead.export import CSV_FIELDS, write_leads
from marketing_lead.models import LeadCandidate
from marketing_lead.scoring import score_lead


class ScoringExportTests(unittest.TestCase):
    def test_existing_customer_is_flagged_but_capped(self) -> None:
        lead = LeadCandidate(
            name="Basik",
            category="amenity:pub",
            latitude=40.0,
            longitude=-73.0,
            source="openstreetmap",
            source_id="node:1",
            address_1="323 Graham Ave",
            phone="3478897597",
            website="https://example.com",
            opening_hours="Mo-Fr 10:00-20:00",
            customer_id="C123",
            lead_status="existing_customer",
        )

        score_lead(lead)

        self.assertLessEqual(lead.confidence_score, 60)
        self.assertIn("matched_internal_customer", lead.signals)
        self.assertIn("existing_customer_not_new_lead", lead.warnings)

    def test_csv_fields_include_verification_columns(self) -> None:
        required = {
            "lead_status",
            "customer_id",
            "customer_status",
            "customer_branch",
            "customer_last_visit",
            "customer_last_shopped",
            "customer_match_confidence",
            "verification_summary",
            "verification_sources",
        }

        self.assertTrue(required.issubset(set(CSV_FIELDS)))

        lead = LeadCandidate(
            name="Basik",
            category="amenity:pub",
            latitude=40.0,
            longitude=-73.0,
            source="openstreetmap",
            source_id="node:1",
            customer_id="C123",
            verification_summary="Matched internal customer.",
            verification_sources=["customer_snapshot"],
        )
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(lead.as_dict())

        output = buffer.getvalue()
        self.assertIn("customer_id", output)
        self.assertIn("verification_summary", output)
        self.assertIn("customer_snapshot", output)

    def test_xlsx_export_includes_parameters_logs_and_leads(self) -> None:
        lead = LeadCandidate(
            name="Basik",
            category="amenity:pub",
            latitude=40.0,
            longitude=-73.0,
            source="openstreetmap",
            source_id="node:1",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "leads.xlsx"
            write_leads(
                [lead],
                output_path,
                "xlsx",
                parameters={"zip": "11211", "radius_mi": 1.5},
                source_reports=[
                    {
                        "name": "openstreetmap",
                        "label": "OpenStreetMap / Overpass",
                        "status": "ok",
                        "count": 1,
                        "detail": "test source",
                    }
                ],
                run_log=[
                    {
                        "timestamp": "2026-05-14T00:00:00+00:00",
                        "progress": 100,
                        "stage": "complete",
                        "message": "Search complete with 1 leads.",
                        "current_lead": "",
                    }
                ],
            )

            with ZipFile(output_path) as archive:
                workbook = archive.read("xl/workbook.xml").decode("utf-8")
                params_sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                log_sheet = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
                leads_sheet = archive.read("xl/worksheets/sheet4.xml").decode("utf-8")

            self.assertIn("Parameters", workbook)
            self.assertIn("Source Reports", workbook)
            self.assertIn("Run Log", workbook)
            self.assertIn("Leads", workbook)
            self.assertIn("11211", params_sheet)
            self.assertIn("Search complete with 1 leads.", log_sheet)
            self.assertIn("Basik", leads_sheet)


if __name__ == "__main__":
    unittest.main()
