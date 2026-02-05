"""Servicio de ingest: orquesta adaptadores y genera observaciones."""

from __future__ import annotations

import logging

from bugresolutionradar.adapters import (
    FilesystemCSVAdapter,
    FilesystemJSONAdapter,
    JiraAdapter,
    JiraConfig,
    XlsxAdapter,
)
from bugresolutionradar.adapters.base import Adapter
from bugresolutionradar.config import Settings
from bugresolutionradar.domain.models import ObservedIncident
from bugresolutionradar.logging_utils import get_logger

logger = get_logger(__name__)


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
        if "jira" in enabled:
            adapters.append(
                JiraAdapter(
                    "jira",
                    JiraConfig(
                        base_url=getattr(self._settings, "jira_base_url", ""),
                        user_email=getattr(self._settings, "jira_user_email", ""),
                        api_token=getattr(self._settings, "jira_api_token", ""),
                        jql=getattr(self._settings, "jira_jql", ""),
                        filter_id=getattr(self._settings, "jira_filter_id", None),
                        max_results=getattr(self._settings, "jira_max_results", 500),
                        page_size=getattr(self._settings, "jira_page_size", 100),
                        timeout_sec=getattr(self._settings, "jira_timeout_sec", 30.0),
                        verify_ssl=getattr(self._settings, "jira_verify_ssl", True),
                        auth_mode=getattr(self._settings, "jira_auth_mode", "auto"),
                        oauth_consumer_key=getattr(
                            self._settings, "jira_oauth_consumer_key", ""
                        ),
                        oauth_access_token=getattr(
                            self._settings, "jira_oauth_access_token", ""
                        ),
                        oauth_private_key=getattr(
                            self._settings, "jira_oauth_private_key", ""
                        ),
                        session_cookie=getattr(self._settings, "jira_session_cookie", ""),
                    ),
                )
            )

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Adapters enabled: %s", [adapter.source_id() for adapter in adapters])
        return adapters

    def ingest(self) -> list[ObservedIncident]:
        """Ejecuta la lectura de todas las fuentes y concatena resultados."""
        observations: list[ObservedIncident] = []
        for adapter in self.build_adapters():
            logger.debug("Reading adapter: %s", adapter.source_id())
            observations.extend(adapter.read())
        logger.debug("Total observations: %s", len(observations))
        return observations
