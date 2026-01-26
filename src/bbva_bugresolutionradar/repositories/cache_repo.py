from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from bbva_bugresolutionradar.domain.models import CacheDocument


class CacheRepo:
    def __init__(self, cache_path: str) -> None:
        self._path = Path(cache_path)

    def load(self) -> CacheDocument:
        if not self._path.exists():
            return CacheDocument(generated_at=datetime.now().astimezone())

        data = json.loads(self._path.read_text(encoding="utf-8"))
        return CacheDocument.model_validate(data)

    def save(self, doc: CacheDocument) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = doc.model_dump(mode="json")
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
