from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reputation.config import REPO_ROOT
from reputation.state_store import state_store_enabled, sync_from_state, sync_to_state


class ReputationOverridesRepo:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict[str, dict[str, Any]]:
        if state_store_enabled():
            sync_from_state(self._path, repo_root=REPO_ROOT)
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
            # Compat: mapa plano id -> override
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
        if state_store_enabled():
            sync_to_state(self._path, repo_root=REPO_ROOT)
