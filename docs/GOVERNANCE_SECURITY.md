# GOVERNANCE_SECURITY.md (EN / ES)

Governance and security model aligned with the current repository.

Back to docs index: `../README.md`

---

## EN | Governance

- Configs are source-of-truth for scope and peer groups.
- Reputation configs can be split across multiple JSON files (mergeable).
- Log and cache artifacts are generated, not committed.
- UI exposure can be controlled per scope via `ui.incidents_enabled` / `ui.ops_enabled`.
- Frontend can also hide the incident scope via `NEXT_PUBLIC_INCIDENTS_ENABLED`.
- If `data/cache/bugresolutionradar_cache.json` is missing, incident scope is hidden regardless of flags.
- Noise control rules are enforced at ingestion time (actor presence + geo allowlists).

### Change management
- Version `data/reputation/*.json` changes.
- Keep a short decision log for taxonomy/keyword changes.
- Re-run ingestion after config changes (hash changes invalidate cache).

---

## EN | Security

- Secrets live in local env files:
  - `backend/bugresolutionradar/.env`
  - `backend/reputation/.env.reputation`
  - `frontend/brr-frontend/.env.local`
- `.env*.example` files are committed; real `.env` files are ignored.
- Logs are written under `./logs/` and ignored by git.

---

## ES | Gobierno

- Las configs son la fuente de verdad del scope y peers.
- Reputacion soporta varios JSON (mergeables).
- Logs y caches se generan localmente y no se versionan.
- La UI se puede modular por scope via `ui.incidents_enabled` / `ui.ops_enabled`.
- El frontend tambien puede ocultar incidencias via `NEXT_PUBLIC_INCIDENTS_ENABLED`.
- Si falta `data/cache/bugresolutionradar_cache.json`, el ambito de incidencias se oculta.
- El control de ruido se aplica en ingesta (actor obligatorio + allowlist por geo).

### Gestion de cambios
- Versiona cambios en `data/reputation/*.json`.
- Mantener un decision log para cambios de taxonomias/keywords.
- Re-ejecuta ingestas al cambiar config (el hash invalida el cache).

---

## ES | Seguridad

- Los secretos viven en .env locales:
  - `backend/bugresolutionradar/.env`
  - `backend/reputation/.env.reputation`
  - `frontend/brr-frontend/.env.local`
- `.env*.example` se versionan; los `.env` reales no.
- Logs en `./logs/` (ignorado por git).
