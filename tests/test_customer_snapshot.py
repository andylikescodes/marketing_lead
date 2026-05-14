from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from marketing_lead.customer_snapshot import (
    ACTIVE_CUSTOMER_STATUS,
    FIELD_NAMES,
    _create_schema,
    _insert_sql,
    apply_customer_matches,
    normalize_address,
    normalize_name,
    normalize_phone,
    zip5,
)
from marketing_lead.models import LeadCandidate


class CustomerSnapshotTests(unittest.TestCase):
    def test_matches_by_phone(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "customers.sqlite"
            _write_customer(path, business="Basik", phone="3478897597", zip_code="11211")
            lead = _lead(name="Other Name", phone="+1 347-889-7597", postcode="11211")

            count, detail = apply_customer_matches([lead], snapshot_path=path)

            self.assertEqual(count, 1)
            self.assertIn("Matched 1", detail)
            self.assertEqual(lead.lead_status, "existing_customer")
            self.assertEqual(lead.customer_id, "C123")
            self.assertIn("customer_match_phone", lead.signals)

    def test_closed_customer_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "customers.sqlite"
            _write_customer(
                path,
                business="Basik",
                phone="3478897597",
                zip_code="11211",
                status="C",
            )
            lead = _lead(name="Basik", phone="+1 347-889-7597", postcode="11211")

            count, detail = apply_customer_matches([lead], snapshot_path=path)

            self.assertEqual(count, 0)
            self.assertIn("Matched 0", detail)
            self.assertEqual(lead.lead_status, "new_lead")
            self.assertEqual(lead.customer_id, "")

    def test_matches_by_zip_and_address(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "customers.sqlite"
            _write_customer(path, business="Basik", address1="323 Graham Avenue", phone="", zip_code="11211")
            lead = _lead(name="Basik Bar", address_1="323 Graham Ave", postcode="11211")

            count, _ = apply_customer_matches([lead], snapshot_path=path)

            self.assertEqual(count, 1)
            self.assertIn("customer_match_zip_address", lead.signals)

    def test_same_address_with_conflicting_name_is_not_automatic_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "customers.sqlite"
            _write_customer(path, business="Basik", address1="323 Graham Avenue", phone="", zip_code="11211")
            lead = _lead(name="Different Restaurant", address_1="323 Graham Ave", postcode="11211")

            count, _ = apply_customer_matches([lead], snapshot_path=path)

            self.assertEqual(count, 0)
            self.assertEqual(lead.lead_status, "new_lead")

    def test_llm_reviewer_can_confirm_ambiguous_address_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "customers.sqlite"
            _write_customer(path, business="Basik", address1="323 Graham Avenue", phone="", zip_code="11211")
            lead = _lead(name="Different DBA", address_1="323 Graham Ave", postcode="11211")

            def reviewer(_lead, customer, candidate_reason):
                self.assertEqual(customer["customer_id"], "C123")
                self.assertEqual(candidate_reason, "zip_address_ambiguous")
                return True, 91, "Same location and DBA confirmed by reviewer."

            count, _ = apply_customer_matches([lead], snapshot_path=path, match_reviewer=reviewer)

            self.assertEqual(count, 1)
            self.assertIn("customer_match_llm_zip_address_ambiguous", lead.signals)
            self.assertIn("DBA confirmed", lead.verification_summary)

    def test_matches_by_zip_and_business_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "customers.sqlite"
            _write_customer(path, business="Basik LLC", address1="999 Other St", phone="", zip_code="11211")
            lead = _lead(name="Basik", address_1="323 Graham Ave", postcode="11211")

            count, _ = apply_customer_matches([lead], snapshot_path=path)

            self.assertEqual(count, 1)
            self.assertIn("customer_match_zip_name", lead.signals)

    def test_missing_snapshot_is_non_fatal(self) -> None:
        lead = _lead(name="Basik")

        count, detail = apply_customer_matches([lead], snapshot_path=Path("missing.sqlite"))

        self.assertEqual(count, 0)
        self.assertIn("not found", detail)
        self.assertIn("customer_snapshot_missing", lead.warnings)


def _lead(
    name: str,
    phone: str = "",
    address_1: str = "",
    postcode: str = "",
) -> LeadCandidate:
    return LeadCandidate(
        name=name,
        category="amenity:pub",
        latitude=40.0,
        longitude=-73.0,
        source="openstreetmap",
        source_id="node:1",
        phone=phone,
        address_1=address_1,
        postcode=postcode,
    )


def _write_customer(
    path: Path,
    business: str,
    address1: str = "323 Graham Avenue",
    phone: str = "3478897597",
    zip_code: str = "11211",
    status: str = ACTIVE_CUSTOMER_STATUS,
) -> None:
    values = {
        "branch": "1",
        "status": status,
        "customer_id": "C123",
        "record_date": "2026-01-01",
        "business": business,
        "address1": address1,
        "address2": "",
        "city": "Brooklyn",
        "state": "NY",
        "zip": zip_code,
        "phone": phone,
        "sic": "",
        "category": "",
        "fmr": "",
        "fmr_status": "",
        "fmr_last_visit": "",
        "opened": "",
        "first_visit": "",
        "last_visit": "2026-01-02",
        "visits": "3",
        "closed": "",
        "last_edit": "",
        "dept_category": "",
        "tax_category": "",
        "address_verified": "Y",
        "last_shopped": "2026-01-03",
    }
    record = tuple(
        [
            *(values[name] for name in FIELD_NAMES),
            normalize_name(values["business"]),
            normalize_address(" ".join([values["address1"], values["address2"]]).strip()),
            normalize_phone(values["phone"]),
            zip5(values["zip"]),
        ]
    )
    connection = sqlite3.connect(path)
    try:
        _create_schema(connection)
        connection.execute(_insert_sql(), record)
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
