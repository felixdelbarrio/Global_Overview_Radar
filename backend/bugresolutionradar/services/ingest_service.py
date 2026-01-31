"""Servicio de ingest: orquesta adaptadores y genera observaciones."""

from __future__ import annotations

from bugresolutionradar.adapters import (
    FilesystemCSVAdapter,
    FilesystemJSONAdapter,
    XlsxAdapter,
)
from bugresolutionradar.adapters.base import Adapter
from bugresolutionradar.config import Settings
from bugresolutionradar.domain.models import ObservedIncident


class IngestService:
    """Orquestador de lectura de fuentes configuradas."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_adapters(self) -> list[Adapter]:
        """Construye la lista de adaptadores segun Settings.sources."""
        adapters: list[Adapter] = []
        # Use `model_dump()` to prefer explicit constructor overrides from pydantic-settings
        cfg = {}
        try:
            cfg = self._settings.model_dump()
        except Exception:
            cfg = {}

        sources_val = cfg.get("sources", getattr(self._settings, "sources", ""))
        assets_dir_val = cfg.get(
            "assets_dir", getattr(self._settings, "assets_dir", "./data/assets")
        )

        enabled = set([s.strip() for s in sources_val.split(",") if s.strip()])

        if "filesystem_json" in enabled:
            adapters.append(FilesystemJSONAdapter("filesystem_json", assets_dir_val))
        if "filesystem_csv" in enabled:
            adapters.append(FilesystemCSVAdapter("filesystem_csv", assets_dir_val))
        if "filesystem_xlsx" in enabled:
            adapters.append(XlsxAdapter("filesystem_xlsx", assets_dir_val))

        return adapters

    def ingest(self) -> list[ObservedIncident]:
        """Ejecuta la lectura de todas las fuentes y concatena resultados."""
        observations: list[ObservedIncident] = []
        for adapter in self.build_adapters():
            observations.extend(adapter.read())
        return observations
