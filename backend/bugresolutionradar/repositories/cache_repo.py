"""Repositorio de cache en JSON (lectura/escritura)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from bugresolutionradar.domain.models import CacheDocument


class CacheRepo:
    """Acceso a cache consolidado almacenado como JSON."""

    def __init__(self, cache_path: str) -> None:
        self._path = Path(cache_path)

    def load(self) -> CacheDocument:
        """Carga el cache; si no existe, devuelve un CacheDocument vacio."""
        if not self._path.exists():
            return CacheDocument(generated_at=datetime.now().astimezone())

        data = json.loads(self._path.read_text(encoding="utf-8"))
        return CacheDocument.model_validate(data)

    def save(self, doc: CacheDocument) -> None:
        """Guarda el documento consolidado en disco."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = doc.model_dump(mode="json")
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
