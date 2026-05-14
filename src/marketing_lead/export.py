from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

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
    "lead_status",
    "customer_id",
    "customer_status",
    "customer_branch",
    "customer_last_visit",
    "customer_last_shopped",
    "customer_match_confidence",
    "signals",
    "warnings",
    "llm_notes",
    "verification_summary",
    "verification_sources",
]

PARAMETER_FIELDS = ["parameter", "value"]
SOURCE_REPORT_FIELDS = ["name", "label", "status", "count", "detail"]
RUN_LOG_FIELDS = ["timestamp", "progress", "stage", "message", "current_lead"]


def write_leads(
    leads: list[LeadCandidate],
    output_path: Path,
    output_format: str,
    parameters: dict[str, object] | None = None,
    source_reports: list[dict[str, object]] | None = None,
    run_log: list[dict[str, object]] | None = None,
    extra_sheets: list[tuple[str, list[str], list[dict[str, object]]]] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        _write_csv(leads, output_path)
    elif output_format == "json":
        _write_json(leads, output_path)
    elif output_format == "xlsx":
        _write_xlsx(
            leads,
            output_path,
            parameters=parameters or {},
            source_reports=source_reports or [],
            run_log=run_log or [],
            extra_sheets=extra_sheets or [],
        )
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


def _write_xlsx(
    leads: list[LeadCandidate],
    output_path: Path,
    parameters: dict[str, object],
    source_reports: list[dict[str, object]],
    run_log: list[dict[str, object]],
    extra_sheets: list[tuple[str, list[str], list[dict[str, object]]]],
) -> None:
    sheets = [
        ("Parameters", [PARAMETER_FIELDS, *_parameter_rows(parameters)]),
        ("Source Reports", [SOURCE_REPORT_FIELDS, *_dict_rows(source_reports, SOURCE_REPORT_FIELDS)]),
        ("Run Log", [RUN_LOG_FIELDS, *_dict_rows(run_log, RUN_LOG_FIELDS)]),
        ("Leads", [CSV_FIELDS, *[_lead_row(lead) for lead in leads]]),
    ]
    for name, fields, records in extra_sheets:
        sheets.append((name, [fields, *_dict_rows(records, fields)]))

    with ZipFile(output_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types(len(sheets)))
        archive.writestr("_rels/.rels", _root_relationships())
        archive.writestr("xl/workbook.xml", _workbook_xml(sheets))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships(len(sheets)))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (_, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(rows))


def _parameter_rows(parameters: dict[str, object]) -> list[list[str]]:
    rows = []
    for key in sorted(parameters):
        rows.append([str(key), _cell_text(parameters[key])])
    if not rows:
        rows.append(["generated_at", datetime.now(timezone.utc).isoformat()])
    return rows


def _dict_rows(records: list[dict[str, object]], fields: list[str]) -> list[list[str]]:
    return [[_cell_text(record.get(field, "")) for field in fields] for record in records]


def _lead_row(lead: LeadCandidate) -> list[str]:
    payload = lead.as_dict()
    return [_cell_text(payload.get(field, "")) for field in CSV_FIELDS]


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_cell_text(item) for item in value)
    return _clean_xml_text(str(value))


def _clean_xml_text(value: str) -> str:
    return "".join(ch for ch in value if ch in "\t\n\r" or ord(ch) >= 32)


def _content_types(sheet_count: int) -> str:
    overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  {overrides}
</Types>"""


def _root_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook_xml(sheets: list[tuple[str, list[list[str]]]]) -> str:
    sheet_tags = "\n".join(
        f'    <sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{sheet_tags}
  </sheets>
</workbook>"""


def _workbook_relationships(sheet_count: int) -> str:
    relationships = [
        f'  <Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    ]
    relationships.append(
        f'  <Relationship Id="rId{sheet_count + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{chr(10).join(relationships)}
</Relationships>"""


def _worksheet_xml(rows: list[list[str]]) -> str:
    column_count = max((len(row) for row in rows), default=1)
    columns = "\n".join(
        f'    <col min="{index}" max="{index}" width="{_column_width(rows, index - 1)}" customWidth="1"/>'
        for index in range(1, column_count + 1)
    )
    row_tags = "\n".join(_row_xml(row, row_index) for row_index, row in enumerate(rows, start=1))
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
    </sheetView>
  </sheetViews>
  <cols>
{columns}
  </cols>
  <sheetData>
{row_tags}
  </sheetData>
  <autoFilter ref="A1:{_column_letter(column_count)}{max(1, len(rows))}"/>
  <pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>
</worksheet>"""


def _row_xml(row: list[str], row_index: int) -> str:
    cells = "\n".join(
        _cell_xml(value, row_index=row_index, column_index=column_index)
        for column_index, value in enumerate(row, start=1)
    )
    return f'    <row r="{row_index}">\n{cells}\n    </row>'


def _cell_xml(value: str, row_index: int, column_index: int) -> str:
    reference = f"{_column_letter(column_index)}{row_index}"
    style = ' s="1"' if row_index == 1 else ""
    escaped = escape(value, {'"': "&quot;"})
    return f'      <c r="{reference}" t="inlineStr"{style}><is><t>{escaped}</t></is></c>'


def _column_width(rows: list[list[str]], column_index: int) -> int:
    values = [row[column_index] for row in rows if column_index < len(row)]
    max_len = max((len(value) for value in values), default=8)
    return min(max(max_len + 2, 10), 60)


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
  <dxfs count="0"/>
  <tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>"""
