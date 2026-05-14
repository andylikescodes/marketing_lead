# Marketing Lead Discovery Prototype

This is a first-pass in-house lead discovery pipeline for finding foodservice businesses near a ZIP code and exporting a field-ready CSV.

The current implementation uses:

- U.S. Census 2025 ZCTA Gazetteer data for ZIP/ZCTA center points.
- OpenStreetMap via Overpass API for restaurants, cafes, bars, bakeries, groceries, caterers, and related foodservice places.
- California ABC daily license data for California alcohol-license validation.
- Optional Ollama review notes through the local Ollama API.
- A conservative confidence score that treats one-source records as discovery leads, not final verified leads.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
marketing-lead collect --zip 11211 --radius-mi 1 --out data/leads_11211.csv
```

You can also run without installing:

```bash
PYTHONPATH=src python3 -m marketing_lead collect --zip 11211 --radius-mi 1 --out data/leads_11211.csv
```

The command writes CSV by default. Use `--format json` for JSON output.

## Local Web App

```bash
PYTHONPATH=src python3 -m marketing_lead serve --host 127.0.0.1 --port 8787
```

Open:

```text
http://127.0.0.1:8787
```

The web app lets you enter a ZIP code, select a radius, include California ABC licenses, optionally ask Ollama for short lead notes, and download CSV output.

For California ZIP codes, the app currently uses California ABC's daily public license export as a free validation source. This is useful for restaurants, bars, groceries, liquor stores, and brewpubs with alcohol licenses or active applications.

## Why This Is Only Layer One

OpenStreetMap is useful for broad discovery and can be stored under its license terms, but it is not enough to dispatch FMRs confidently. A production-grade system should cross-check each lead against independent sources:

- Google Places API for current business status and high-quality POI matching.
- Yelp/Foursquare for independent consumer-directory confirmation.
- Local health inspection, business license, liquor license, and tax/permit data where available.
- Website/domain signals, phone validation, and address type validation.
- Internal Restaurant Depot history: existing account, failed visit, closed/wrong-address disposition, signup outcome.

Important: Google Places content has restrictive caching/storage rules. Use it as a live verification signal or store only fields allowed by your agreement, such as Place IDs. Do not build the persistent master database by scraping Google Maps.

## Output Fields

The CSV includes:

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

This repository currently creates the discovery layer and a conservative first score. It is designed so additional validation connectors can be added without changing the CSV contract.

## Optional Ollama Review

If Ollama is running locally, the app can call:

```text
http://localhost:11434/api/chat
```

The default model is `kimi-k2.6:cloud`. LLM notes are intentionally treated as review notes, not factual validation. The score only gets a small bump when the LLM successfully reviews a lead.
