from __future__ import annotations

from pathlib import Path

from bbva_bugresolutionradar.adapters.base import Adapter


class FilesystemAdapter(Adapter):
    def __init__(self, source_id: str, assets_dir: str) -> None:
        self._source_id = source_id
        self._assets_dir = Path(assets_dir)

    def source_id(self) -> str:
        return self._source_id

    def assets_dir(self) -> Path:
        return self._assets_dir
