"""Base para adaptadores que leen ficheros desde el sistema de archivos."""

from __future__ import annotations

from pathlib import Path

from bbva_bugresolutionradar.adapters.base import Adapter


class FilesystemAdapter(Adapter):
    """Adaptador base para fuentes filesystem.

    Mantiene source_id y ruta base de assets para reutilizacion en subclases.
    """

    def __init__(self, source_id: str, assets_dir: str) -> None:
        self._source_id = source_id
        self._assets_dir = Path(assets_dir)

    def source_id(self) -> str:
        """Devuelve el identificador de la fuente."""
        return self._source_id

    def assets_dir(self) -> Path:
        """Devuelve la ruta base de assets como Path."""
        return self._assets_dir
