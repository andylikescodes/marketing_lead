from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from marketing_lead.artifacts import read_discovery_bundle, write_discovery_bundle
from marketing_lead.models import LeadCandidate, ZipLocation
from marketing_lead.pipeline import LeadSearchResult, SourceReport


class ArtifactTests(unittest.TestCase):
    def test_discovery_bundle_round_trip(self) -> None:
        result = LeadSearchResult(
            zip_code="90015",
            radius_mi=2.0,
            location=ZipLocation("90015", 34.03931, -118.26626, "test"),
            source_reports=[
                SourceReport(
                    name="openstreetmap",
                    label="OpenStreetMap / Overpass",
                    count=1,
                    status="ok",
                    detail="test source",
                )
            ],
            leads=[
                LeadCandidate(
                    name="Test Restaurant",
                    category="amenity:restaurant",
                    address_1="123 Main St",
                    city="Los Angeles",
                    state="CA",
                    postcode="90015",
                    latitude=34.0,
                    longitude=-118.0,
                    source="openstreetmap",
                    source_id="node:1",
                    signals=["has_name"],
                    warnings=["single_source_only"],
                )
            ],
            merged_count=0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "discovery.json"
            write_discovery_bundle(
                path,
                result,
                parameters={"zip": "90015", "workflow_part": "cloud_discovery"},
                run_log=[{"stage": "complete", "message": "done"}],
            )

            loaded, parameters, run_log = read_discovery_bundle(path)

        self.assertEqual(parameters["zip"], "90015")
        self.assertEqual(run_log[0]["stage"], "complete")
        self.assertEqual(loaded.zip_code, "90015")
        self.assertEqual(loaded.source_reports[0].name, "openstreetmap")
        self.assertEqual(loaded.leads[0].name, "Test Restaurant")
        self.assertEqual(loaded.leads[0].signals, ["has_name"])
        self.assertEqual(loaded.leads[0].warnings, ["single_source_only"])


if __name__ == "__main__":
    unittest.main()
