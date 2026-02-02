# MENTAL_MODEL.md (EN / ES)

Back to root: `../README.md`

---

## EN | How to think about the system

Do not think in terms of raw volume or dashboards.
Think in terms of:
- scope defined by configuration
- reproducible ingestion
- explainable comparisons
- low-noise signals that protect the end-user experience

Current UI bias:
- sentiment is primary; incidents are optional and contextual

Change the system by:
- adding/removing JSON configs in `data/reputation/`
- toggling sources in `.env.reputation`
- running ingestion to refresh caches

---

## ES | Modelo mental

No pienses en volumen bruto ni en dashboards.
Piensa en:
- scope definido por configuracion
- ingesta reproducible
- comparativas explicables
- senales con bajo ruido que protejan la experiencia del cliente

Sesgo actual de UI:
- sentimiento primero; incidencias opcionales y contextuales

Cambias el sistema:
- anadiendo/eliminando JSON en `data/reputation/`
- activando fuentes en `.env.reputation`
- ejecutando ingestas para refrescar caches
