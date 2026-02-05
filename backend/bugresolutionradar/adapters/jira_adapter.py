"""Adapter JIRA: lee Bugs desde una vista (JQL o filtro) via API REST."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterable, Iterator
from urllib.parse import urlsplit

import httpx

from bugresolutionradar.adapters.base import Adapter
from bugresolutionradar.adapters.utils import to_str
from bugresolutionradar.domain.enums import Severity, Status
from bugresolutionradar.domain.models import ObservedIncident
from bugresolutionradar.logging_utils import get_logger

logger = get_logger(__name__)

_JIRA_UI_PATH_MARKERS = (
    "/secure/",
    "/browse/",
    "/projects/",
    "/issues/",
)


class JiraAPIError(RuntimeError):
    """Error amigable para fallos en la API de JIRA."""


def _jira_date(raw: str | None) -> date | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    if "T" in value:
        value = value.split("T", 1)[0]
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _map_status(fields: dict[str, Any]) -> Status:
    status_obj = fields.get("status") or {}
    if not isinstance(status_obj, dict):
        status_obj = {}

    name = to_str(status_obj.get("name")) or ""
    name_lc = name.lower()

    if "block" in name_lc or "bloque" in name_lc:
        return Status.BLOCKED

    category = status_obj.get("statusCategory") or {}
    if not isinstance(category, dict):
        category = {}
    category_key = to_str(category.get("key")) or ""
    category_key_lc = category_key.lower()

    if category_key_lc == "done":
        return Status.CLOSED
    if category_key_lc == "indeterminate":
        return Status.IN_PROGRESS
    if category_key_lc == "new":
        return Status.OPEN

    if "progress" in name_lc or "progreso" in name_lc:
        return Status.IN_PROGRESS
    if "close" in name_lc or "cerr" in name_lc or "resuelto" in name_lc:
        return Status.CLOSED
    if "open" in name_lc or "abiert" in name_lc:
        return Status.OPEN

    return Status.UNKNOWN


def _map_severity(fields: dict[str, Any]) -> Severity:
    priority = fields.get("priority") or {}
    if not isinstance(priority, dict):
        priority = {}
    name = (to_str(priority.get("name")) or "").strip()
    if not name:
        return Severity.UNKNOWN
    s = name.lower()

    if any(token in s for token in ("p0", "blocker", "highest", "critical", "crit")):
        return Severity.CRITICAL
    if any(token in s for token in ("p1", "high", "major", "alta")):
        return Severity.HIGH
    if any(token in s for token in ("p2", "medium", "normal", "media", "med")):
        return Severity.MEDIUM
    if any(token in s for token in ("p3", "low", "minor", "baja")):
        return Severity.LOW
    return Severity.UNKNOWN


def _safe_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _normalize_jira_base_url(raw: str) -> str:
    """Normaliza JIRA_BASE_URL a un "site base URL".

    En JIRA es común pegar una URL de UI tipo:
    - https://mi-jira/secure/Dashboard.jspa
    - https://mi-jira/jira/secure/Dashboard.jspa  (con context-path)

    Para la API REST necesitamos la raíz del sitio (incluyendo context-path si aplica):
    - https://mi-jira
    - https://mi-jira/jira
    """

    value = (raw or "").strip()
    if not value:
        return ""

    # Si el usuario pega "jira.miempresa.com" sin esquema, asumimos https.
    if "://" not in value:
        value = f"https://{value}"

    parts = urlsplit(value)
    if not parts.netloc:
        return value.rstrip("/")

    scheme = parts.scheme or "https"
    netloc = parts.netloc
    path = (parts.path or "").strip()
    if not path or path == "/":
        return f"{scheme}://{netloc}"

    path_lc = path.lower()
    cut_positions: list[int] = []

    # Si nos pasan un endpoint REST completo, recortamos antes de /rest/api...
    rest_idx = path_lc.find("/rest/api")
    if rest_idx != -1:
        cut_positions.append(rest_idx)

    # Marcadores típicos de UI
    for marker in _JIRA_UI_PATH_MARKERS:
        idx = path_lc.find(marker)
        if idx != -1:
            cut_positions.append(idx)

    # UI legacy: *.jspa
    jspa_idx = path_lc.find(".jspa")
    if jspa_idx != -1:
        slash_idx = path.rfind("/", 0, jspa_idx)
        cut_positions.append(max(0, slash_idx))

    prefix = path
    if cut_positions:
        prefix = path[: min(cut_positions)]

    prefix = prefix.rstrip("/")
    return f"{scheme}://{netloc}{prefix}" if prefix else f"{scheme}://{netloc}"


def _extract_jira_error_detail(resp: httpx.Response | None) -> str | None:
    if resp is None:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    parts: list[str] = []
    error_messages = data.get("errorMessages")
    if isinstance(error_messages, list):
        for msg in error_messages:
            if isinstance(msg, str) and msg.strip():
                parts.append(msg.strip())

    errors = data.get("errors")
    if isinstance(errors, dict):
        for key, value in errors.items():
            if not key:
                continue
            if isinstance(value, str) and value.strip():
                parts.append(f"{key}: {value.strip()}")
            elif value:
                parts.append(f"{key}: {value}")

    return " | ".join(parts) if parts else None


def _discover_base_url_from_rest_url(url: str) -> str | None:
    url_lc = url.lower()
    idx = url_lc.find("/rest/api/")
    if idx == -1:
        return None
    return url[:idx].rstrip("/")


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    user_email: str
    api_token: str
    jql: str
    filter_id: str | None = None
    max_results: int = 500
    page_size: int = 100
    timeout_sec: float = 30.0
    verify_ssl: bool = True


class JiraAdapter(Adapter):
    """Adapter que consulta issues en JIRA y los normaliza a ObservedIncident."""

    def __init__(self, source_id: str, config: JiraConfig, client: httpx.Client | None = None):
        self._source_id = source_id
        self._cfg = config
        self._client = client
        self._base_url = _normalize_jira_base_url(config.base_url)

        raw = (config.base_url or "").strip().rstrip("/")
        if raw and self._base_url and raw != self._base_url:
            logger.debug(
                "[JiraAdapter] Normalized JIRA_BASE_URL from %r to %r", raw, self._base_url
            )

    def source_id(self) -> str:
        return self._source_id

    def read(self) -> list[ObservedIncident]:
        cfg = self._cfg
        base_url = (self._base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("JIRA_BASE_URL is required (e.g. https://tu-org.atlassian.net)")
        if not cfg.api_token.strip():
            raise ValueError("JIRA_API_TOKEN is required")
        if not cfg.user_email.strip():
            raise ValueError("JIRA_USER_EMAIL is required")

        observed_at = datetime.now().astimezone()
        with self._client_context() as client:
            jql = self._resolve_jql(client)
            if not jql.strip():
                raise ValueError("JIRA_JQL (or JIRA_FILTER_ID) is required")
            issues = self._search(client, jql)
        items: list[ObservedIncident] = []
        for issue in issues:
            key = to_str(issue.get("key")) or ""
            if not key:
                continue
            fields = issue.get("fields") or {}
            if not isinstance(fields, dict):
                fields = {}
            summary = to_str(fields.get("summary")) or ""
            created = _jira_date(to_str(fields.get("created")))
            updated = _jira_date(to_str(fields.get("updated")))
            resolved = _jira_date(to_str(fields.get("resolutiondate")))
            resolution = fields.get("resolution") if isinstance(fields.get("resolution"), dict) else {}
            resolution_name = to_str(resolution.get("name")) if isinstance(resolution, dict) else None

            components = _safe_items(fields.get("components"))
            component_names = [to_str(c.get("name")) for c in components if to_str(c.get("name"))]
            product = component_names[0] if component_names else None

            items.append(
                ObservedIncident(
                    source_id=self.source_id(),
                    source_key=key,
                    observed_at=observed_at,
                    title=summary,
                    status=_map_status(fields),
                    severity=_map_severity(fields),
                    opened_at=created,
                    updated_at=updated,
                    closed_at=resolved,
                    clients_affected=None,
                    product=product,
                    feature=None,
                    resolution_type=resolution_name,
                )
            )
        logger.debug("[JiraAdapter] Observed incidents: %s", len(items))
        return items

    @contextmanager
    def _client_context(self) -> Iterator[httpx.Client]:
        if self._client is not None:
            yield self._client
            return
        cfg = self._cfg
        auth = httpx.BasicAuth(cfg.user_email, cfg.api_token)
        headers = {"Accept": "application/json"}
        with httpx.Client(
            base_url=self._base_url.rstrip("/"),
            auth=auth,
            headers=headers,
            timeout=cfg.timeout_sec,
            verify=cfg.verify_ssl,
            follow_redirects=True,
        ) as client:
            yield client

    def _candidate_base_urls(self) -> list[str]:
        base = (self._base_url or "").rstrip("/")
        if not base:
            return []

        candidates = [base]
        try:
            parts = urlsplit(base)
            if parts.path in ("", "/"):
                candidates.append(f"{base}/jira")
        except Exception:
            pass

        out: list[str] = []
        seen = set()
        for candidate in candidates:
            normalized = candidate.rstrip("/")
            if not normalized or normalized in seen:
                continue
            out.append(normalized)
            seen.add(normalized)
        return out

    def _url(self, path: str, base_url: str | None = None) -> str:
        base = (base_url or self._base_url or "").rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    def _raise_non_404(self, exc: httpx.HTTPStatusError) -> None:
        resp = exc.response
        status_code = resp.status_code if resp is not None else None
        detail = _extract_jira_error_detail(resp)
        if detail:
            raise JiraAPIError(f"JIRA request failed ({status_code}): {detail}") from exc
        raise JiraAPIError(f"JIRA request failed ({status_code}).") from exc

    def _parse_json_dict(self, resp: httpx.Response) -> dict[str, Any]:
        content_type = (resp.headers.get("content-type") or "").lower()
        try:
            data = resp.json()
        except Exception as exc:
            hint = (
                f"Unexpected JIRA response (non-JSON; content-type={content_type or 'unknown'}). "
                "This often means SSO/login HTML or an incorrect JIRA_BASE_URL "
                "(some instances require adding /jira)."
            )
            raise JiraAPIError(hint) from exc
        if not isinstance(data, dict):
            raise JiraAPIError("Invalid JIRA response (expected JSON object)")
        return data

    def _update_base_url_from_response(self, resp: httpx.Response) -> None:
        discovered = _discover_base_url_from_rest_url(str(resp.url))
        if not discovered:
            return
        discovered = discovered.rstrip("/")
        if discovered and discovered != self._base_url:
            logger.debug("[JiraAdapter] Discovered base URL from response: %r", discovered)
            self._base_url = discovered

    def _resolve_jql(self, client: httpx.Client) -> str:
        cfg = self._cfg
        if cfg.jql.strip():
            return cfg.jql.strip()
        if cfg.filter_id and cfg.filter_id.strip():
            filter_id = cfg.filter_id.strip()
            first_error: Exception | None = None
            for base_url in self._candidate_base_urls():
                for api_version in ("3", "2"):
                    resp = client.get(
                        self._url(f"rest/api/{api_version}/filter/{filter_id}", base_url)
                    )
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if exc.response is not None and exc.response.status_code == 404:
                            first_error = first_error or exc
                            continue
                        self._raise_non_404(exc)
                    data = self._parse_json_dict(resp)
                    self._update_base_url_from_response(resp)
                    jql = to_str(data.get("jql")) or ""
                    if jql.strip():
                        return jql.strip()

            if first_error is not None:
                raise ValueError("JIRA_FILTER_ID not found or does not expose a JQL")
            raise ValueError("Unable to resolve JQL from JIRA filter")
        return ""

    def _search(self, client: httpx.Client, jql: str) -> list[dict[str, Any]]:
        cfg = self._cfg
        max_results = max(1, int(cfg.max_results))
        page_size = max(1, min(250, int(cfg.page_size)))
        fields = [
            "summary",
            "status",
            "priority",
            "created",
            "updated",
            "resolutiondate",
            "resolution",
            "components",
        ]
        start_at = 0
        out: list[dict[str, Any]] = []

        def do_search(api_version: str, base_url: str) -> dict[str, Any]:
            params: dict[str, str | int] = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": min(page_size, max_results - len(out)),
                "fields": ",".join(fields),
            }
            resp = client.get(self._url(f"rest/api/{api_version}/search", base_url), params=params)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    raise
                self._raise_non_404(exc)
            data = self._parse_json_dict(resp)
            self._update_base_url_from_response(resp)
            return data

        api_versions: Iterable[str] = ("3", "2")
        first_error: Exception | None = None

        for candidate_base_url in self._candidate_base_urls():
            active_base_url = candidate_base_url
            for api_version in api_versions:
                start_at = 0
                out = []
                try:
                    while len(out) < max_results:
                        data = do_search(api_version, active_base_url)
                        active_base_url = (self._base_url or active_base_url).rstrip("/")

                        issues = data.get("issues")
                        if issues is None:
                            break
                        if not isinstance(issues, list):
                            raise JiraAPIError("Invalid JIRA response: 'issues' is not a list")
                        if not issues:
                            break

                        for issue in issues:
                            if isinstance(issue, dict):
                                out.append(issue)
                                if len(out) >= max_results:
                                    break

                        total = data.get("total")
                        if isinstance(total, int) and start_at + len(issues) >= total:
                            break
                        start_at += len(issues)

                    logger.info(
                        "[JiraAdapter] Loaded %s issues via api/%s (max=%s)",
                        len(out),
                        api_version,
                        max_results,
                    )
                    return out
                except JiraAPIError:
                    raise
                except httpx.HTTPStatusError as exc:
                    if exc.response is not None and exc.response.status_code == 404:
                        first_error = first_error or exc
                        continue
                    raise

        if first_error:
            raise first_error
        return out
