from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from reputation.actors import build_actor_alias_map, canonicalize_actor
from reputation.models import ReputationCacheDocument

try:  # optional fast json
    import orjson  # type: ignore

    def _read_json(path: Path) -> dict:
        return orjson.loads(path.read_bytes())

    def _write_json(path: Path, payload: dict) -> None:
        path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))

except Exception:  # pragma: no cover - optional dependency

    def _read_json(path: Path) -> dict:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(path: Path, payload: dict) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


_ALIAS_MAP_CACHE: dict[str, str] = {}
_ALIAS_MAP_MTIME: float | None = None
_ALIAS_MAP_PATH: Path | None = None


def _load_alias_map(config_file: Path) -> dict[str, str]:
    global _ALIAS_MAP_CACHE, _ALIAS_MAP_MTIME, _ALIAS_MAP_PATH
    if not config_file.exists():
        _ALIAS_MAP_CACHE = {}
        _ALIAS_MAP_MTIME = None
        _ALIAS_MAP_PATH = None
        return {}
    try:
        mtime = config_file.stat().st_mtime
    except OSError:
        mtime = None
    if config_file == _ALIAS_MAP_PATH and mtime == _ALIAS_MAP_MTIME:
        return _ALIAS_MAP_CACHE
    try:
        with config_file.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        alias_map = build_actor_alias_map(cfg)
    except Exception:
        alias_map = {}
    _ALIAS_MAP_CACHE = alias_map
    _ALIAS_MAP_MTIME = mtime
    _ALIAS_MAP_PATH = config_file
    return alias_map


class ReputationCacheRepo:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._cached_doc: ReputationCacheDocument | None = None
        self._cached_mtime: float | None = None

    def load(self) -> Optional[ReputationCacheDocument]:
        if not self._path.exists():
            return None
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            mtime = None
        if self._cached_doc is not None and self._cached_mtime == mtime:
            return self._cached_doc

        data = _read_json(self._path)
        doc = ReputationCacheDocument.model_validate(data)

        # Cargar aliases desde el fichero central de configuración
        # `data/reputation/config.json` si está disponible. Este fichero
        # contiene la sección `otros_actores_aliases` con la forma:
        # { "CanonicalName": ["alias1", "alias2"] }
        config_file = Path(__file__).resolve().parents[3] / "data" / "reputation" / "config.json"
        alias_map = _load_alias_map(config_file)

        for item in doc.items:
            if item.actor:
                normalized = canonicalize_actor(item.actor, alias_map) if alias_map else item.actor
                if normalized:
                    item.actor = normalized

        self._cached_doc = doc
        self._cached_mtime = mtime
        return doc

    def save(self, doc: ReputationCacheDocument) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(self._path, doc.model_dump(mode="json"))
        try:
            self._cached_mtime = self._path.stat().st_mtime
        except OSError:
            self._cached_mtime = None
        self._cached_doc = doc

    def is_fresh(self, ttl_hours: int) -> bool:
        doc = self.load()
        if doc is None:
            return False
        now = datetime.now(timezone.utc)
        age_hours = (now - doc.generated_at).total_seconds() / 3600.0
        return age_hours <= ttl_hours
