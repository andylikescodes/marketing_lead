# Architecture Notes

The system is designed around a source-union strategy:

```text
ZIP input
  -> Census ZCTA centroid
  -> free source collectors
  -> normalize records
  -> merge likely duplicates
  -> score validation signals
  -> web table / CSV export
```

## Current Free Sources

1. U.S. Census ZCTA Gazetteer
   - Used to turn a ZIP/ZCTA into a latitude/longitude search center.
   - Cached locally under `~/.cache/marketing_lead`.

2. OpenStreetMap / Overpass
   - Used for broad POI discovery.
   - Categories include restaurants, fast food, cafes, bars, pubs, food courts, bakeries, delis, butcher/seafood shops, supermarkets, convenience stores, beverage/alcohol shops, and caterers.
   - Best for recall, but records can be stale or incomplete.

3. California ABC Daily License Export
   - Used for California ZIPs only.
   - Adds active alcohol license/application signals for restaurants, bars, grocery/liquor, brewpubs, and related businesses.
   - Best as a validation source. It will not find every restaurant because many restaurants do not have ABC licenses.

4. Census Geocoder
   - Implemented as an optional address geocoder.
   - Disabled by default in the interactive flow because per-address online geocoding can be slow.

5. Ollama
   - Optional review layer.
   - It can summarize/classify leads based on fields already collected.
   - It should not be treated as proof that a business is open.

## Scoring Philosophy

The current score is intentionally conservative:

- OSM-only discovery leads are capped at 69.
- California ABC-only leads are capped at 78.
- Multi-source free leads are capped at 92.
- Active California ABC licenses add a strong validation signal.
- Missing street addresses hurt the score.

This avoids making free-only data look more certain than it is.

## What Boam Or Paid Vendors Still Have

The main gap is not AI alone. It is source coverage and freshness:

- Paid POI/business feeds.
- Continuous closure/opening monitoring.
- More mature entity resolution.
- CRM/data warehouse sync.
- Web/menu/social/job-posting monitoring.
- Historical field outcome feedback across many customers.

The in-house advantage will come from combining free sources with Restaurant Depot's internal customer and FMR outcome data.

## Next Milestones

1. Import existing customer list and suppress current customers.
2. Add an FMR outcome file: open, closed, residential, duplicate, already customer, signed up.
3. Add county/city health inspection datasets for priority markets.
4. Add batch geocoding for source records without coordinates.
5. Add source-specific refresh timestamps and stale-data warnings.
6. Add a simple analyst review workflow for accepting/rejecting leads.
