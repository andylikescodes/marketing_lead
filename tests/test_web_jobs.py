from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from marketing_lead.models import LeadCandidate, ZipLocation
from marketing_lead.pipeline import LeadSearchResult
from marketing_lead.web import JOBS, JOBS_LOCK, _create_job, _result_to_csv


class WebJobTests(unittest.TestCase):
    def setUp(self) -> None:
        with JOBS_LOCK:
            JOBS.clear()

    def test_job_completes_and_export_reuses_result(self) -> None:
        def fake_search_leads(**kwargs):
            callback = kwargs.get("progress_callback")
            if callback:
                callback({"progress": 50, "stage": "fake", "message": "Halfway."})
            return LeadSearchResult(
                zip_code="11211",
                radius_mi=1.0,
                location=ZipLocation("11211", 40.0, -73.0, "test"),
                source_reports=[],
                leads=[
                    LeadCandidate(
                        name="Basik",
                        category="amenity:pub",
                        latitude=40.0,
                        longitude=-73.0,
                        source="openstreetmap",
                        source_id="node:1",
                    )
                ],
                merged_count=0,
            )

        params = {"zip": ["11211"], "radius_mi": ["1"], "limit": ["1"], "include_llm": ["false"]}
        with patch("marketing_lead.web.search_leads", side_effect=fake_search_leads):
            job = _create_job(params)
            completed = _wait_for_job(job.id)

        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.progress, 100)
        self.assertIsNotNone(completed.result)

        csv_payload = _result_to_csv(completed.result)
        self.assertIn("lead_status", csv_payload)
        self.assertIn("Basik", csv_payload)


def _wait_for_job(job_id: str):
    deadline = time.time() + 5
    while time.time() < deadline:
        with JOBS_LOCK:
            job = JOBS[job_id]
            if job.status in {"completed", "failed"}:
                return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


if __name__ == "__main__":
    unittest.main()
