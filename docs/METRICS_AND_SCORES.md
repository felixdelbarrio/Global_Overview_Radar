# METRICS_AND_SCORES.md (EN / ES)

Back to signals: `SIGNALS_CATALOG.md`

---

## EN | Current metrics (BugResolutionRadar)

Computed in `backend/bugresolutionradar/domain/kpis.py`:
- Open incidents (total + by severity)
- New incidents in period (total + by severity)
- New masters (over threshold of affected clients)
- Closed incidents in period (total + by severity)
- Mean resolution time (overall + by severity)
- Stale open incidents (older than threshold)

These KPIs are exposed via `/kpis` and summarized by the frontend.

---

## EN | Reputation metrics (current state)

Reputation currently powers:
- Sentiment summary (positive / neutral / negative counts, average score)
- Sentiment by geo (table)
- Comparative accumulated sentiment series (principal vs other actors)
- Dashboard overlay with incident trend (if enabled)

Downloads:
- CSV export for chart series and filtered listings.

---

## ES | Metricas actuales (BugResolutionRadar)

Calculadas en `backend/bugresolutionradar/domain/kpis.py`:
- Incidencias abiertas (total + por severidad)
- Incidencias nuevas en el periodo (total + por severidad)
- Nuevas masters (superan el umbral de clientes)
- Incidencias cerradas en el periodo (total + por severidad)
- Tiempo medio de resolucion (global + por severidad)
- Incidencias abiertas obsoletas (sobre el umbral)

Los KPIs se exponen via `/kpis` y el frontend los resume.

---

## ES | Metricas de reputacion (estado actual)

Reputacion ya alimenta:
- Resumen de sentimiento (conteos + score medio)
- Sentimiento por pais
- Serie acumulada comparativa (actor principal vs otros)
- Dashboard con tendencia de incidencias (si esta habilitado)

Descargas:
- Export CSV del grafico y del listado filtrado.
