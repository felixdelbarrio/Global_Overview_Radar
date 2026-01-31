# GOVERNANCE_SECURITY.md (EN / ES)

Enterprise-grade governance and security model.

Back to docs index: [`../README.md`](../README.md)

---

## EN | Governance

### Ownership
Define explicit owners for:
- taxonomies
- peer groups
- sensitivity mappings
- source registry

### Change management
- version configurations
- require review for taxonomy changes
- keep an audit trail of changes impacting scores/signals

### Explainability governance
Ensure every signal links to:
- evidence
- baseline definition
- peer group definition
- configuration version

---

## EN | Security model

### Isolation
- logical tenant isolation per organization
- separate storage namespaces (recommended)

### Access control
- RBAC for API and dashboards
- permission by market, topic, and source type (optional)

### Evidence-level controls
- ability to restrict which sources can be surfaced as evidence
- redact sensitive metadata when needed

---

## ES | Gobierno

### Ownership
Propietarios explícitos de:
- taxonomías
- peer groups
- mapeos de sensibilidad
- registro de fuentes

### Gestión de cambios
- versionar configuración
- revisión obligatoria para cambios de taxonomía
- auditoría de cambios que impactan scores/señales

### Gobierno de explicabilidad
Cada señal debe enlazar a:
- evidencia
- definición de baseline
- definición de peer group
- versión de configuración

---

## ES | Modelo de seguridad

### Aislamiento
- aislamiento lógico por organización (tenant)
- espacios de almacenamiento separados (recomendado)

### Control de acceso
- RBAC para API y dashboards
- permisos por mercado, tema y tipo de fuente (opcional)

### Control a nivel de evidencia
- restringir qué fuentes pueden mostrarse como evidencia
- redactar metadatos sensibles cuando aplique
