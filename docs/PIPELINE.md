# Pipeline

## Ingest flow
1. Trigger ingest via `POST /ingest/reputation` or `make reputation-ingest`.
2. Collectors fetch raw mentions from the enabled sources.
3. Normalization applies actor aliases and geo mappings.
4. Enrichment computes sentiment, rating, and aspect signals.
5. The cache snapshot is written to `data/cache/reputation_cache.json`.
6. The API serves filtered slices for the UI.

## Job tracking
Ingest jobs are persisted in memory and exposed at:
- `GET /ingest/jobs`
- `GET /ingest/jobs/{job_id}`

## Common run modes
- Local development: run the ingest, then start the API and frontend.
- Batch refresh: schedule `make reputation-ingest` on a cadence and serve the
  cache with a long TTL.
