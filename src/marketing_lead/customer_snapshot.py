from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from marketing_lead.models import LeadCandidate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "customer_snapshot.sqlite"
ACTIVE_CUSTOMER_STATUS = "A"

CUSTOMER_SQL = """
SELECT
    [Branch],
    [Status],
    [CustomerID],
    [RecordDate],
    [Business],
    [Address1],
    [Address2],
    [City],
    [State],
    [Zip],
    [Phone],
    [SIC],
    [Category],
    [FMR],
    [FMRStatus],
    [FMRLastVisit],
    [Opened],
    [FirstVisit],
    [LastVisit],
    [Visits],
    [Closed],
    [LastEdit],
    [DeptCategory],
    [TaxCategory],
    [AddressVerified],
    [LastShopped]
FROM [GLOBAL].[dbo].[Customers] WITH (NOLOCK)
WHERE [Status] = 'A'
"""

FIELD_NAMES = [
    "branch",
    "status",
    "customer_id",
    "record_date",
    "business",
    "address1",
    "address2",
    "city",
    "state",
    "zip",
    "phone",
    "sic",
    "category",
    "fmr",
    "fmr_status",
    "fmr_last_visit",
    "opened",
    "first_visit",
    "last_visit",
    "visits",
    "closed",
    "last_edit",
    "dept_category",
    "tax_category",
    "address_verified",
    "last_shopped",
]

CUSTOMER_EXPORT_FIELDS = [
    "branch",
    "status",
    "customer_id",
    "business",
    "address1",
    "address2",
    "city",
    "state",
    "zip",
    "phone",
    "category",
    "fmr",
    "fmr_status",
    "last_visit",
    "last_shopped",
]


@dataclass(frozen=True)
class CustomerMatch:
    customer_id: str
    branch: str
    status: str
    business: str
    address1: str
    city: str
    state: str
    zip_code: str
    phone: str
    last_visit: str
    last_shopped: str
    confidence: int
    reason: str


def refresh_customer_snapshot(
    output_path: Path = DEFAULT_SNAPSHOT_PATH,
    server: str = "CORPORATE-DW",
    database: str = "GLOBAL",
    driver: str = "ODBC Driver 17 for SQL Server",
    batch_size: int = 5000,
) -> int:
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("pyodbc is required for customer refresh. Install it with: pip install pyodbc") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    connection_string = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes"
    try:
        source = pyodbc.connect(connection_string)
    except pyodbc.Error:
        fallback = f"DRIVER={{SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes"
        source = pyodbc.connect(fallback)

    row_count = 0
    try:
        cursor = source.cursor()
        cursor.execute(CUSTOMER_SQL)
        target = sqlite3.connect(output_path)
        try:
            _create_schema(target)
            insert_sql = _insert_sql()
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                records = [_normalize_record(row) for row in rows]
                target.executemany(insert_sql, records)
                row_count += len(records)
            target.commit()
        finally:
            target.close()
    finally:
        source.close()

    return row_count


def apply_customer_matches(
    leads: list[LeadCandidate],
    snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
) -> tuple[int, str]:
    if not snapshot_path.exists():
        detail = f"Customer snapshot not found at {snapshot_path}. Run `marketing-lead customers refresh`."
        for lead in leads:
            _append_unique(lead.warnings, "customer_snapshot_missing")
        return 0, detail

    matched = 0
    connection = sqlite3.connect(snapshot_path)
    try:
        connection.row_factory = sqlite3.Row
        for lead in leads:
            match = find_customer_match(connection, lead)
            if match:
                matched += 1
                apply_match(lead, match)
    finally:
        connection.close()
    return matched, f"Matched {matched} leads against local customer snapshot."


def active_customers_for_zip(
    zip_code: str,
    snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
    limit: int = 10000,
) -> list[dict[str, object]]:
    if not snapshot_path.exists():
        return []

    normalized_zip = zip5(zip_code)
    connection = sqlite3.connect(snapshot_path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT {", ".join(CUSTOMER_EXPORT_FIELDS)}
            FROM customers
            WHERE status = ? AND zip5 = ?
            ORDER BY branch, business, customer_id
            LIMIT ?
            """,
            (ACTIVE_CUSTOMER_STATUS, normalized_zip, limit),
        ).fetchall()
        return [{field: str(row[field] or "") for field in CUSTOMER_EXPORT_FIELDS} for row in rows]
    finally:
        connection.close()


def find_customer_match(connection: sqlite3.Connection, lead: LeadCandidate) -> CustomerMatch | None:
    phone = normalize_phone(lead.phone)
    if len(phone) >= 10:
        row = connection.execute(
            """
            SELECT * FROM customers
            WHERE status = ? AND norm_phone = ?
            ORDER BY last_visit DESC
            LIMIT 1
            """,
            (ACTIVE_CUSTOMER_STATUS, phone),
        ).fetchone()
        if row:
            return _row_to_match(row, confidence=96, reason="phone")

    zip_code = zip5(lead.postcode)
    address = normalize_address(lead.address_1)
    if zip_code and address:
        row = connection.execute(
            """
            SELECT * FROM customers
            WHERE status = ? AND zip5 = ? AND norm_address = ?
            ORDER BY last_visit DESC
            LIMIT 1
            """,
            (ACTIVE_CUSTOMER_STATUS, zip_code, address),
        ).fetchone()
        if row:
            return _row_to_match(row, confidence=90, reason="zip_address")

    name = normalize_name(lead.name)
    if zip_code and name:
        row = connection.execute(
            """
            SELECT * FROM customers
            WHERE status = ? AND zip5 = ? AND norm_name = ?
            ORDER BY last_visit DESC
            LIMIT 1
            """,
            (ACTIVE_CUSTOMER_STATUS, zip_code, name),
        ).fetchone()
        if row:
            return _row_to_match(row, confidence=86, reason="zip_name")

        candidates = connection.execute(
            """
            SELECT * FROM customers
            WHERE status = ? AND zip5 = ? AND norm_name <> ''
            LIMIT 1000
            """,
            (ACTIVE_CUSTOMER_STATUS, zip_code),
        ).fetchall()
        best_row = None
        best_ratio = 0.0
        for candidate in candidates:
            ratio = SequenceMatcher(None, name, candidate["norm_name"]).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_row = candidate
        if best_row and best_ratio >= 0.88:
            return _row_to_match(best_row, confidence=int(82 + (best_ratio - 0.88) * 50), reason="zip_fuzzy_name")

    return None


def apply_match(lead: LeadCandidate, match: CustomerMatch) -> None:
    lead.lead_status = "existing_customer"
    lead.customer_id = match.customer_id
    lead.customer_status = match.status
    lead.customer_branch = match.branch
    lead.customer_last_visit = match.last_visit
    lead.customer_last_shopped = match.last_shopped
    lead.customer_match_confidence = match.confidence
    _append_unique(lead.signals, "matched_internal_customer")
    _append_unique(lead.signals, f"customer_match_{match.reason}")
    _append_unique(lead.warnings, "existing_customer_not_new_lead")
    _append_unique(lead.verification_sources, "customer_snapshot")
    summary = (
        f"Matched existing customer {match.customer_id}"
        f" ({match.business}) by {match.reason.replace('_', ' ')}."
    )
    lead.verification_summary = _join_summary(lead.verification_summary, summary)


def normalize_name(value: str) -> str:
    value = value.lower()
    value = re.sub(r"&", " and ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = f" {value} "
    for suffix in [" inc ", " llc ", " corp ", " corporation ", " co ", " ltd ", " restaurant "]:
        value = value.replace(suffix, " ")
    return " ".join(value.split())


def normalize_address(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9#]+", " ", value)
    replacements = {
        " street ": " st ",
        " avenue ": " ave ",
        " boulevard ": " blvd ",
        " road ": " rd ",
        " drive ": " dr ",
        " suite ": " ste ",
        " highway ": " hwy ",
        " place ": " pl ",
    }
    value = f" {value} "
    for before, after in replacements.items():
        value = value.replace(before, after)
    return " ".join(value.split())


def normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def zip5(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:5]


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS customers;
        CREATE TABLE customers (
            branch TEXT,
            status TEXT,
            customer_id TEXT,
            record_date TEXT,
            business TEXT,
            address1 TEXT,
            address2 TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,
            phone TEXT,
            sic TEXT,
            category TEXT,
            fmr TEXT,
            fmr_status TEXT,
            fmr_last_visit TEXT,
            opened TEXT,
            first_visit TEXT,
            last_visit TEXT,
            visits TEXT,
            closed TEXT,
            last_edit TEXT,
            dept_category TEXT,
            tax_category TEXT,
            address_verified TEXT,
            last_shopped TEXT,
            norm_name TEXT,
            norm_address TEXT,
            norm_phone TEXT,
            zip5 TEXT
        );
        CREATE INDEX idx_customers_phone ON customers(norm_phone);
        CREATE INDEX idx_customers_zip_address ON customers(zip5, norm_address);
        CREATE INDEX idx_customers_zip_name ON customers(zip5, norm_name);
        """
    )


def _insert_sql() -> str:
    columns = [*FIELD_NAMES, "norm_name", "norm_address", "norm_phone", "zip5"]
    placeholders = ", ".join("?" for _ in columns)
    return f"INSERT INTO customers ({', '.join(columns)}) VALUES ({placeholders})"


def _normalize_record(row: Iterable[object]) -> tuple[str, ...]:
    values = [_stringify(value) for value in row]
    record = dict(zip(FIELD_NAMES, values))
    full_address = " ".join(part for part in [record["address1"], record["address2"]] if part)
    return (
        *values,
        normalize_name(record["business"]),
        normalize_address(full_address),
        normalize_phone(record["phone"]),
        zip5(record["zip"]),
    )


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def _row_to_match(row: sqlite3.Row, confidence: int, reason: str) -> CustomerMatch:
    return CustomerMatch(
        customer_id=str(row["customer_id"] or ""),
        branch=str(row["branch"] or ""),
        status=str(row["status"] or ""),
        business=str(row["business"] or ""),
        address1=str(row["address1"] or ""),
        city=str(row["city"] or ""),
        state=str(row["state"] or ""),
        zip_code=str(row["zip"] or ""),
        phone=str(row["phone"] or ""),
        last_visit=str(row["last_visit"] or row["fmr_last_visit"] or ""),
        last_shopped=str(row["last_shopped"] or ""),
        confidence=max(0, min(confidence, 100)),
        reason=reason,
    )


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _join_summary(existing: str, addition: str) -> str:
    if not existing:
        return addition
    return f"{existing} {addition}"
