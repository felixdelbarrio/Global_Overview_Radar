# Data contracts

This document summarizes the configuration and cache shapes used by Global
Overview Radar. It is intentionally high-level so it stays accurate as the
system evolves.

## Business configuration (JSON)
Config files live in `data/reputation/*.json` and are merged into a single
runtime config. Typical sections include:
- Principal actor definition and aliases.
- Geographic lists and geo aliases.
- Source configuration and query templates.
- Domain-specific prompt templates for enrichment.

Keep configuration additive and avoid overwriting unrelated keys in new files.

## Cache snapshot
The main cache snapshot is stored at `data/cache/reputation_cache.json` and is
served by `/reputation/items`. It contains:
- `generated_at`: ISO timestamp of the snapshot.
- `config_hash`: hash of the merged config used for the run.
- `sources_enabled`: list of sources active in the run.
- `items`: list of reputation items.

Each item typically contains:
- `id`, `source`, `actor`, `geo`, `language`
- `published_at`, `collected_at`
- `title`, `text`, `url`, `author`
- `signals` (ratings, sentiment score, source-specific fields)
- `sentiment`, `aspects`, `manual_override`

## Overrides
Manual overrides are stored at `data/cache/reputation_overrides.json` with:
- `updated_at`
- `items`: map from item id to override values (`geo`, `sentiment`, `note`).
