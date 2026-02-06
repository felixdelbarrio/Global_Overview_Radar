# API

Base API: FastAPI app in `backend/reputation/api/main.py`.

## Health
- `GET /health`

## Reputation
- `GET /reputation/meta`
  - Returns active profiles, available sources, and cache status.
- `GET /reputation/items`
  - Filters: `from_date`, `to_date`, `sentiment`, `entity`, `geo`, `sources`.
- `POST /reputation/items/compare`
  - Accepts a list of filter objects to compare multiple segments.
- `POST /reputation/items/override`
  - Sets manual overrides for items (`ids`, optional `geo`, `sentiment`, `note`).

## Settings and profiles
- `GET /reputation/settings`
- `POST /reputation/settings`
- `POST /reputation/settings/reset`
- `GET /reputation/profiles`
- `POST /reputation/profiles`

## Ingest
- `POST /ingest/reputation`
- `GET /ingest/jobs`
- `GET /ingest/jobs/{job_id}`
