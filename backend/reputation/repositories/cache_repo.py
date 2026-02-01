from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from reputation.actors import build_actor_alias_map, canonicalize_actor
from reputation.models import ReputationCacheDocument


class ReputationCacheRepo:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Optional[ReputationCacheDocument]:
        if not self._path.exists():
            return None
        import json
        from pathlib import Path

        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        doc = ReputationCacheDocument.model_validate(data)

        # Cargar aliases desde el fichero central de configuración
        # `data/reputation/config.json` si está disponible. Este fichero
        # contiene la sección `otros_actores_aliases` con la forma:
        # { "CanonicalName": ["alias1", "alias2"] }
        config_file = Path(__file__).resolve().parents[3] / "data" / "reputation" / "config.json"
        alias_map: dict[str, str] = {}
        if config_file.exists():
            try:
                with config_file.open("r", encoding="utf-8") as f:
                    cfg = json.load(f)
                alias_map = build_actor_alias_map(cfg)
            except Exception:
                alias_map = {}

        for item in doc.items:
            if item.actor:
                normalized = canonicalize_actor(item.actor, alias_map) if alias_map else item.actor
                if normalized:
                    item.actor = normalized

        return doc

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
