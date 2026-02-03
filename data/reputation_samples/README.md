# Global Overview Radar — Sample config.json packs

Todos mantienen la **misma estructura** que tu config actual (news/forums/blogs/appstore/etc).

## Cómo usar
1. Copia el JSON que quieras a tu ruta de config (p. ej. `./data/reputation/config.json`).
2. En `.env.reputation` apunta al archivo con `REPUTATION_CONFIG_PATH=./data/reputation/config.json`.
3. (Opcional) Si quieres LLM, crea `data/reputation_llm/<perfil>_llm.json` (puedes copiarlo desde `data/reputation_llm_samples/`).
4. Activa fuentes recomendadas en `.env.reputation`: `REPUTATION_SOURCE_NEWS=true`, `REPUTATION_SOURCE_FORUMS=true`, `REPUTATION_SOURCE_BLOGS_RSS=true` (opcional `REPUTATION_SOURCE_TRUSTPILOT=true`).
5. Ejecuta: `brr-reputation --force`.

## Notas
- Los feeds de “markets” aquí son **señales indirectas** (Google News RSS con `site:play.google.com` / `site:apps.apple.com`).
  Para reviews reales, rellena `appstore.app_ids` y/o `google_reviews.place_ids` y activa esas fuentes.
- Ajusta límites en `.env.reputation` si te crece demasiado el volumen:
  - `NEWS_SITE_QUERY_MAX_TOTAL`, `NEWS_MAX_RSS_URLS`, `NEWS_MAX_ARTICLES`


- Perfil retail bancario (banco principal + países + filial) con foco en **app issues, fraude, comisiones, Bizum/transferencias**, reguladores y comparativa multi-geo.
