from __future__ import annotations

from bbva_bugresolutionradar.adapters import FilesystemCSVAdapter, FilesystemJSONAdapter, XlsxAdapter
from bbva_bugresolutionradar.adapters.base import Adapter
from bbva_bugresolutionradar.config import Settings
from bbva_bugresolutionradar.domain.models import ObservedIncident


class IngestService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_adapters(self) -> list[Adapter]:
        adapters: list[Adapter] = []
        enabled = set(self._settings.enabled_sources())

        if "filesystem_json" in enabled:
            adapters.append(FilesystemJSONAdapter("filesystem_json", self._settings.assets_dir))
        if "filesystem_csv" in enabled:
            adapters.append(FilesystemCSVAdapter("filesystem_csv", self._settings.assets_dir))
        if "filesystem_xlsx" in enabled:
            adapters.append(XlsxAdapter("filesystem_xlsx", self._settings.assets_dir))

        return adapters

    def ingest(self) -> list[ObservedIncident]:
        observations: list[ObservedIncident] = []
        for adapter in self.build_adapters():
            observations.extend(adapter.read())
        return observations