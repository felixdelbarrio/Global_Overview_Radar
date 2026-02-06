# Architecture

## Overview
Global Overview Radar is a two-tier system: a Python + FastAPI backend and a
Next.js frontend. The backend ingests public signals, normalizes actors and
geographies, enriches each mention with sentiment and rating signals, and writes
cache snapshots. The frontend reads from the API and renders the sentiment
intelligence dashboard.

## Core components
- Collectors: `backend/reputation/collectors`
- Normalization: `backend/reputation/actors`, `backend/reputation/config`
- Enrichment: `backend/reputation/services` (sentiment, rating, signals)
- Cache: `backend/reputation/repositories/cache_repo.py`
- API: `backend/reputation/api`
- Frontend: `frontend/brr-frontend`

## Data flow
1. An ingest job is triggered (API or CLI).
2. Collectors fetch raw mentions from configured sources.
3. Normalization applies actor aliases and geo mappings.
4. Enrichment computes sentiment, ratings, and aspect signals.
5. A cache snapshot is written to `data/cache/reputation_cache.json`.
6. The API serves filtered data to the frontend.

## Storage model
The system is file-based by default:
- `data/reputation/*.json`: business configuration and profiles.
- `data/reputation_llm/*.json`: LLM prompt templates aligned to each profile.
- `data/cache/*.json`: generated cache and overrides.

## Extensibility
To add a new source:
- Implement a collector in `backend/reputation/collectors`.
- Add its toggle to `.env.reputation`.
- Update the profile config with source settings and queries.
