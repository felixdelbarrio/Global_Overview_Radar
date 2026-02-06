# Operations

## Local run
Backend:
- `make ensure-backend`
- `make reputation-ingest`
- `make dev-back`

Frontend:
- `make ensure-front`
- `make dev-front`

## Cache lifecycle
- The cache snapshot is written to `data/cache/reputation_cache.json`.
- Delete the cache file to force a fresh ingest.

## Logging
Enable logging in `backend/reputation/.env.reputation`:
- `REPUTATION_LOG_ENABLED=true`
- `REPUTATION_LOG_TO_FILE=true`
- `REPUTATION_LOG_FILE_NAME=reputation.log`

## Overrides
Manual overrides are stored in `data/cache/reputation_overrides.json` and can be
managed via `POST /reputation/items/override`.
