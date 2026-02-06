# Configuration

Global Overview Radar loads configuration from `backend/reputation/.env.reputation`
(autocreated from `.env.reputation.example` when missing).

## Paths
- `REPUTATION_CONFIG_PATH`: directory with business JSON files (default `./data/reputation`).
- `REPUTATION_LLM_CONFIG_PATH`: directory with LLM prompt JSON files (default `./data/reputation_llm`).
- `REPUTATION_CACHE_PATH`: cache snapshot file (default `./data/cache/reputation_cache.json`).
- `REPUTATION_OVERRIDES_PATH`: manual override file (default `./data/cache/reputation_overrides.json`).
- `REPUTATION_PROFILE`: optional profile selector (single name or comma list).

## Source toggles
Each source can be enabled with a boolean env var:
- `REPUTATION_SOURCE_NEWS`, `REPUTATION_SOURCE_FORUMS`, `REPUTATION_SOURCE_BLOGS`,
  `REPUTATION_SOURCE_APPSTORE`, `REPUTATION_SOURCE_TRUSTPILOT`, `REPUTATION_SOURCE_GDELT`,
  `REPUTATION_SOURCE_GOOGLE_REVIEWS`, `REPUTATION_SOURCE_GOOGLE_PLAY`, `REPUTATION_SOURCE_YOUTUBE`,
  `REPUTATION_SOURCE_DOWNDETECTOR`, and others.

To hard-limit the active sources, use:
- `REPUTATION_SOURCES_ALLOWLIST` (comma-separated names).

## Logging
- `REPUTATION_LOG_ENABLED`
- `REPUTATION_LOG_TO_FILE`
- `REPUTATION_LOG_FILE_NAME`
- `REPUTATION_LOG_DEBUG`

## Performance / memory
- `REPUTATION_ITEM_TITLE_MAX`: max title length kept per item (default 400; set 0 to disable).
- `REPUTATION_ITEM_TEXT_MAX`: max text length kept per item (default 8000; set 0 to disable).
- `REPUTATION_HTTP_CACHE_MAX_BYTES`: max cached HTTP response size in bytes (default 1_000_000).
- `REPUTATION_PROFILE_STATE_DISABLED`: set to `true` to ignore `data/cache/reputation_profile.json` (useful for benchmarks).

## Profiles
Profile JSON files are merged in this order:
1. `config.json` if present.
2. Remaining `*.json` files in alphabetical order.

The API exposes the active profile list and the applied source in `/reputation/meta`.
