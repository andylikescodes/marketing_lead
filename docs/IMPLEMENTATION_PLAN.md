# Multi-Source Lead Quality Implementation Plan

This plan converts the current ZIP -> lead discovery -> Excel export workflow into a stronger multi-source quality pipeline while keeping the command-line operator flow stable.

## Target outcome

Given:

- ZIP code
- radius
- output path

The command should:

1. Discover candidates from multiple sources.
2. Normalize and merge records into canonical leads.
3. Score validity/confidence and visit priority.
4. Export an Excel workbook with traceability (`Parameters`, `Source Reports`, `Run Log`, `Leads`).

## Phase 0 - Baseline and guardrails

- Lock acceptance criteria for `marketing-lead collect` and `marketing-lead discover`.
- Add regression checks for workbook sheets and required lead columns.
- Track baseline metrics per pilot ZIP: total leads, multi-source ratio, % with phone, % with full address.

## Phase 1 - Source connector framework (in progress)

- Replace hardcoded source blocks in `search_leads` with a source registry (`LeadSource`).
- Keep per-source error isolation and source reports.
- Preserve existing OSM + Open Brewery DB + optional CA ABC behavior.

Status:

- ✅ Source registry abstraction added.
- ✅ Existing sources migrated.

## Phase 2 - Address normalization and geocoding

- Add Census geocoder enrichment for incomplete addresses and missing coordinates.
- Add local caching + retry/backoff.
- Capture geocoder provenance fields and geocode confidence signals.

## Phase 3 - Health inspection connectors

- Add a reusable Socrata connector utility.
- Implement first county connector for priority market (LA County first).
- Normalize permit/inspection records into lead candidates and verification fields.

## Phase 4 - Dataset discovery automation

- Add a dataset discovery helper (Data.gov CKAN + manual config templates).
- Generate connector starter configs for city/county health and business-license feeds.

## Phase 5 - Entity resolution v2

- Add clustering with fuzzy name/address and distance thresholds.
- Include phone/domain exact match shortcuts.
- Store source provenance per cluster for explainability.

## Phase 6 - Confidence scoring v2

- Move to configurable weighted scoring.
- Add explicit positive/negative signals:
  - source diversity
  - inspection recency
  - address/geocode quality
  - closure/inactive indicators
- Emit quality tiers and recommended action.

## Phase 7 - Opportunity scoring

- Add macro market features (CBP/ZBP + BLS QCEW).
- Add branch-distance and market-density features.
- Emit a separate visit-priority score.

## Phase 8 - Operator workflow and rollout

- Keep one-step CLI for ZIP -> Excel.
- Add profile presets for source combinations.
- Run pilots by region; tune scoring with field outcomes.

## Immediate next steps

1. Add unit tests for the new source registry in pipeline.
2. Add connector health telemetry (latency + row counts) to source reports.
3. Start Phase 2 Census geocoder enrichment behind a feature flag.
