# Global Overview Radar — LLM configs (producción)

En esta carpeta se guardan los JSON de configuración del LLM que **acompañan** a cada config de negocio en `data/reputation/`.

**Convención de nombres**
Si tienes `data/reputation/<perfil>.json`, el LLM debe llamarse:
`data/reputation_llm/<perfil>_llm.json`

Ejemplo:
`data/reputation/<perfil>.json` → `data/reputation_llm/<perfil>_llm.json`

**Estructura mínima**
```json
{
  "models": {
    "llm_model": "gpt-5.2"
  },
  "llm": {
    "system_prompt": "...",
    "batch_size": 12
  }
}
```

**Importante**
Los secretos **no** van en estos JSON. Las API keys y el proveedor se configuran en `.env.reputation`.

**Fallback**
Si falta el `*_llm.json` correspondiente o el LLM falla (cuota/errores), se avisa de forma discreta y se usa el modo de reglas.
