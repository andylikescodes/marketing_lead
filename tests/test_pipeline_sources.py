from __future__ import annotations

import unittest
from unittest.mock import patch

from marketing_lead.models import LeadCandidate, ZipLocation
from marketing_lead.pipeline import SourceReport, _enrich_missing_coordinates, _run_source, LeadSource


class PipelineSourceTests(unittest.TestCase):
    def test_run_source_records_count_and_latency(self) -> None:
        source = LeadSource(
            name="test_source",
            label="Test Source",
            stage="test",
            progress=10,
            detail="test detail",
            message="Running test source",
            collector=lambda _location, _radius: [
                LeadCandidate(
                    name="A",
                    category="amenity:restaurant",
                    latitude=1.0,
                    longitude=2.0,
                    source="test_source",
                    source_id="a1",
                )
            ],
        )
        reports: list[SourceReport] = []
        all_leads: list[LeadCandidate] = []

        _run_source(source, ZipLocation("90015", 34.0, -118.0, "test"), 1000, all_leads, reports)

        self.assertEqual(len(all_leads), 1)
        self.assertEqual(reports[0].count, 1)
        self.assertEqual(reports[0].status, "ok")
        self.assertGreaterEqual(reports[0].duration_ms, 0)

    def test_geocode_enrichment_adds_coordinates_when_missing(self) -> None:
        lead = LeadCandidate(
            name="Missing LatLng",
            category="amenity:cafe",
            latitude=0,
            longitude=0,
            source="openstreetmap",
            source_id="node:2",
            address_1="111 S Grand Ave",
            city="Los Angeles",
            state="CA",
            postcode="90015",
        )
        with patch("marketing_lead.pipeline.geocode_address_details") as mock_geocode:
            from marketing_lead.geocode import GeocodeResult
            mock_geocode.return_value = GeocodeResult(34.05, -118.25, "111 S Grand Ave, Los Angeles, CA", "R")
            _enrich_missing_coordinates([lead])

        self.assertEqual(lead.latitude, 34.05)
        self.assertEqual(lead.longitude, -118.25)
        self.assertIn("census_geocoded", lead.signals)
        self.assertEqual(lead.geocode_source, "census_geocoder")
        self.assertEqual(lead.geocode_confidence, "R")


if __name__ == "__main__":
    unittest.main()
