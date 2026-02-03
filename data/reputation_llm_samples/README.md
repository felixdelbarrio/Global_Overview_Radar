# Global Overview Radar — LLM configs (samples)

Estos JSON son **plantillas** de LLM adaptadas a los perfiles de `data/reputation_samples/`.

**Cómo usarlos**
1. Elige un sample de `data/reputation_samples/` (por ejemplo `banking_bbva_retail.json`).
2. Copia su LLM correspondiente desde `data/reputation_llm_samples/banking_bbva_retail_llm.json`.
3. Pégalo en `data/reputation_llm/` con el mismo nombre: `data/reputation_llm/banking_bbva_retail_llm.json`.

**Convención**
Siempre debe existir el par:
`data/reputation/<perfil>.json` ↔ `data/reputation_llm/<perfil>_llm.json`

**Sin secretos**
Estos JSON no contienen API keys ni credenciales. Todo eso vive en `.env.reputation`.
