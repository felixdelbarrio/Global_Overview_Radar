from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class IncidentsOverridesRepo:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}

        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, dict):
                return {k: v for k, v in items.items() if isinstance(v, dict)}
            return {k: v for k, v in data.items() if isinstance(v, dict)}
        return {}

    def save(self, items: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
