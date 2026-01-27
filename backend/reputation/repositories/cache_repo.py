from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from reputation.models import ReputationCacheDocument


class ReputationCacheRepo:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Optional[ReputationCacheDocument]:
        if not self._path.exists():
            return None
        import json

        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return ReputationCacheDocument.model_validate(data)

    def save(self, doc: ReputationCacheDocument) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        import json

        with self._path.open("w", encoding="utf-8") as f:
            json.dump(doc.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    def is_fresh(self, ttl_hours: int) -> bool:
        doc = self.load()
        if doc is None:
            return False
        now = datetime.now(timezone.utc)
        age_hours = (now - doc.generated_at).total_seconds() / 3600.0
        return age_hours <= ttl_hours
