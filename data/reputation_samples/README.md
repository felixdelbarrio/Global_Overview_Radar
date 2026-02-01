# Global Overview Radar — Sample config.json packs

Este ZIP incluye varios `config.json` “WoW” para sectores distintos.
Todos mantienen la **misma estructura** que tu config actual (news/forums/blogs/appstore/etc).

## Cómo usar
1) Copia el JSON que quieras a tu ruta de config (p. ej. `./data/reputation/config.json`)
2) En `.env.reputation` apunta al archivo:
   - `REPUTATION_CONFIG_PATH=./data/reputation/config.json`
3) Activa fuentes (recomendado para estos samples):
   - `REPUTATION_SOURCE_NEWS=true`
   - `REPUTATION_SOURCE_FORUMS=true`
   - `REPUTATION_SOURCE_BLOGS_RSS=true`
   - (Opcional) `REPUTATION_SOURCE_TRUSTPILOT=true`
4) Ejecuta: `brr-reputation --force`

## Notas
- Los feeds de “markets” aquí son **señales indirectas** (Google News RSS con `site:play.google.com` / `site:apps.apple.com`).
  Para reviews reales, rellena `appstore.app_ids` y/o `google_reviews.place_ids` y activa esas fuentes.
- Ajusta límites en `.env.reputation` si te crece demasiado el volumen:
  - `NEWS_SITE_QUERY_MAX_TOTAL`, `NEWS_MAX_RSS_URLS`, `NEWS_MAX_ARTICLES`


- `banking_bbva_retail_oro_puro.json` — banca retail (BBVA + países + Garanti BBVA) con foco en **app issues, fraude, comisiones, Bizum/transferencias**, reguladores y comparativa multi-geo.
