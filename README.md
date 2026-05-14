# Marketing Lead Discovery Prototype

This is a first-pass in-house lead discovery pipeline for finding foodservice businesses near a ZIP code and exporting a field-ready Excel workbook from the terminal.

The current implementation uses:

- U.S. Census 2025 ZCTA Gazetteer data for ZIP/ZCTA center points.
- OpenStreetMap via Overpass API for restaurants, cafes, bars, bakeries, groceries, caterers, and related foodservice places.
- California ABC daily license data for California alcohol-license validation.
- Open Brewery DB for independent brewery/taproom leads and cross-source confirmation.
- Optional Ollama review notes through the local Ollama API.
- A conservative confidence score that treats one-source records as discovery leads, not final verified leads.

## Quick Start

For local-only runs, use the one-step command:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
marketing-lead collect --zip 11211 --radius-mi 1 --out data/leads_11211.xlsx
```

You can also run without installing:

```bash
PYTHONPATH=src python3 -m marketing_lead collect --zip 11211 --radius-mi 1 --out data/leads_11211.xlsx
```

The command logs progress to the terminal and writes a `.log` file next to the output workbook by default. Use `--log-file data/run.log` to choose a specific log path.

The output format is inferred from `--out`:

- `.xlsx`: Excel workbook with `Parameters`, `Source Reports`, `Run Log`, and `Leads` sheets.
- `.csv`: Lead rows only, useful for importing elsewhere.
- `.json`: Lead rows only as JSON.

You can also force a format with `--format xlsx`, `--format csv`, or `--format json`.

Useful terminal options:

```bash
marketing-lead collect \
  --zip 90015 \
  --radius-mi 3 \
  --min-score 65 \
  --limit 250 \
  --out data/leads_90015.xlsx
```

For California ZIP codes, the pipeline can include California ABC's daily public license export as a free validation source. Use `--no-abc` to skip it.

## Cloud Discovery / Local Validation

For the fuller workflow, split the run into two parts:

1. Run public-source discovery in Codex cloud or another network-enabled environment.
2. Move the discovery JSON bundle back to the local machine.
3. Validate against the local active-customer snapshot and export the final Excel workbook.

Cloud/network discovery:

```bash
PYTHONPATH=src python3 -m marketing_lead discover \
  --zip 90015 \
  --radius-mi 2 \
  --out data/discovery_90015.json
```

Local customer validation:

```bash
PYTHONPATH=src python3 -m marketing_lead validate-customers \
  --in data/discovery_90015.json \
  --out data/leads_90015_validated.xlsx
```

The discovery bundle intentionally does not include customer matching. The local validation step uses `data/customer_snapshot.sqlite`, filters to active customers where `Status = A`, flags already-existing customers, rescoring them below new-lead priority, and adds an `Active Customers in ZIP` workbook sheet.

## Optional Web App

```bash
PYTHONPATH=src python3 -m marketing_lead serve --host 127.0.0.1 --port 8787
```

Open:

```text
http://127.0.0.1:8787
```

The web app is still available for local exploration, but the main workflow is now the backend terminal command and Excel output.

## Why This Is Only Layer One

OpenStreetMap plus Open Brewery DB provide a stronger free baseline for discovery and cross-checking, but they are still not enough to dispatch FMRs confidently. A production-grade system should add additional independent sources:

- Google Places API for current business status and high-quality POI matching.
- Yelp/Foursquare for independent consumer-directory confirmation.
- Local health inspection, business license, liquor license, and tax/permit data where available.
- Website/domain signals, phone validation, and address type validation.
- Internal Restaurant Depot history: existing account, failed visit, closed/wrong-address disposition, signup outcome.

Important: Google Places content has restrictive caching/storage rules. Use it as a live verification signal or store only fields allowed by your agreement, such as Place IDs. Do not build the persistent master database by scraping Google Maps.

## Excel Output

The workbook includes:

- `Parameters`: ZIP, radius, filters, source options, output path, resolved coordinates, and summary counts.
- `Source Reports`: source status, counts, and source-specific details or errors.
- `Run Log`: progress stages and messages captured during the run.
- `Leads`: the scored lead results.

## Lead Fields

The lead sheet includes:

- `name`, `category`, address fields, `latitude`, `longitude`
- `phone`, `website`, `opening_hours`
- `source`, `source_id`
- `confidence_score`
- `signals` and `warnings`

For this prototype, confidence is capped below final-dispatch quality when there is only one source. The next milestone is to add paid/API connectors and source agreement scoring.

## Recommended Production Architecture

1. Discovery: collect candidates by ZIP/radius from OSM plus licensed POI/business datasets.
2. Normalization: standardize names, phones, websites, coordinates, and addresses.
3. Entity resolution: merge records that represent the same business.
4. Validation: check business status, address type, health/business license presence, phone, website, hours, and recent signals.
5. Scoring: produce tiers such as `visit_now`, `call_first`, `research`, and `reject`.
6. Feedback loop: ingest FMR visit outcomes so the model learns which sources and signals predict real open businesses.

## Practical Scoring Target

A lead should usually require at least two independent positive sources before an FMR visit. A strong target:

- 85+: send FMR.
- 70-84: call first or desk verify.
- 50-69: research queue.
- below 50: reject or hold.

This repository currently creates the discovery layer and a conservative first score. It is designed so additional validation connectors can be added without changing the lead field contract used by Excel, CSV, and JSON exports.

## Optional Ollama Review

If Ollama is running locally, the CLI and optional web flow can call:

```text
http://localhost:11434/api/chat
```

The default model is `kimi-k2.6:cloud`. LLM notes are intentionally treated as review notes, not factual validation. The score only gets a small bump when the LLM successfully reviews a lead.
