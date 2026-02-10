from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import ssl
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote_plus, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

SafeElementTree: Any
try:
    # Prefer a hardened XML parser for untrusted RSS/Atom feeds.
    from defusedxml import ElementTree as SafeElementTree  # type: ignore
except Exception:  # pragma: no cover - optional dependency for some dev/test envs
    SafeElementTree = ElementTree

_HTTP_CACHE: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
_HTTP_CACHE_LOCK = Lock()
_HTTP_BLOCKED: dict[str, float] = {}

DEFAULT_HTTP_CACHE_TTL_SEC = 120
DEFAULT_HTTP_CACHE_MAX_ENTRIES = 500
DEFAULT_HTTP_RETRIES = 1
DEFAULT_HTTP_BLOCK_TTL_SEC = 90
DEFAULT_HTTP_MAX_BYTES = 2_000_000


def _safe_url_for_logs(url: str) -> str:
    """Redact query/fragment to avoid leaking API keys in logs."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            return "<invalid-url>"
        port = f":{parsed.port}" if parsed.port else ""
        path = parsed.path or ""
        scheme = parsed.scheme or "http"
        return f"{scheme}://{host}{port}{path}"
    except Exception:
        return "<invalid-url>"


def _is_public_fetch_url(url: str) -> bool:
    """Best-effort SSRF guard for Cloud Run (block localhost/link-local/private IPs)."""
    try:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return False
        if host in {"localhost", "metadata.google.internal"}:
            return False
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return True  # domain name; cannot safely resolve without DNS lookup
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )
    except Exception:
        return False


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on"}


def _read_response(response: Any, max_bytes: int) -> tuple[bytes, bool]:
    if max_bytes <= 0:
        raw = response.read()
        if isinstance(raw, str):
            raw = raw.encode("utf-8", errors="replace")
        elif not isinstance(raw, bytes):
            raw = bytes(raw)
        return raw, False
    remaining = max_bytes
    chunks: list[bytes] = []
    while remaining > 0:
        chunk = response.read(min(65536, remaining))
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8", errors="replace")
        elif not isinstance(chunk, bytes):
            chunk = bytes(chunk)
        chunks.append(chunk)
        remaining -= len(chunk)
    truncated = remaining == 0
    return b"".join(chunks), truncated


def _http_cache_key(url: str, headers: dict[str, str]) -> str:
    if not headers:
        return url
    header_items = sorted(headers.items())
    return f"{url}|{header_items}"


def _http_cache_get(key: str) -> str | None:
    ttl = _env_int("REPUTATION_HTTP_CACHE_TTL_SEC", DEFAULT_HTTP_CACHE_TTL_SEC)
    if ttl <= 0:
        return None
    now = time.time()
    with _HTTP_CACHE_LOCK:
        entry = _HTTP_CACHE.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < now:
            _HTTP_CACHE.pop(key, None)
            return None
        _HTTP_CACHE.move_to_end(key)
        return value


def _http_cache_set(key: str, value: str) -> None:
    ttl = _env_int("REPUTATION_HTTP_CACHE_TTL_SEC", DEFAULT_HTTP_CACHE_TTL_SEC)
    if ttl <= 0:
        return
    expires_at = time.time() + ttl
    with _HTTP_CACHE_LOCK:
        _HTTP_CACHE[key] = (expires_at, value)
        _HTTP_CACHE.move_to_end(key)
        max_entries = _env_int("REPUTATION_HTTP_CACHE_MAX_ENTRIES", DEFAULT_HTTP_CACHE_MAX_ENTRIES)
        if max_entries > 0:
            while len(_HTTP_CACHE) > max_entries:
                _HTTP_CACHE.popitem(last=False)


def _is_blocked(url: str) -> bool:
    ttl = _env_int("REPUTATION_HTTP_BLOCK_TTL_SEC", DEFAULT_HTTP_BLOCK_TTL_SEC)
    if ttl <= 0:
        return False
    host = urlparse(url).netloc
    if not host:
        return False
    now = time.time()
    expires_at = _HTTP_BLOCKED.get(host)
    if expires_at is None:
        return False
    if expires_at < now:
        _HTTP_BLOCKED.pop(host, None)
        return False
    return True


def _block_host(url: str) -> None:
    ttl = _env_int("REPUTATION_HTTP_BLOCK_TTL_SEC", DEFAULT_HTTP_BLOCK_TTL_SEC)
    if ttl <= 0:
        return
    host = urlparse(url).netloc
    if not host:
        return
    _HTTP_BLOCKED[host] = time.time() + ttl


def http_get_text(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> str:
    req_headers = {"User-Agent": "global-overview-radar/0.1"}
    if headers:
        req_headers.update(headers)
    if os.getenv("K_SERVICE") and not _is_public_fetch_url(url):
        logger.warning("blocked outbound fetch on Cloud Run: %s", _safe_url_for_logs(url))
        return ""
    if _is_blocked(url):
        return ""
    cache_key = _http_cache_key(url, req_headers)
    cached = _http_cache_get(cache_key)
    if cached is not None:
        return cached

    retries = max(0, _env_int("REPUTATION_HTTP_RETRIES", DEFAULT_HTTP_RETRIES))
    backoff = max(0.0, _env_float("REPUTATION_HTTP_RETRY_BACKOFF_SEC", 0.4))
    max_bytes = _env_int("REPUTATION_HTTP_MAX_BYTES", DEFAULT_HTTP_MAX_BYTES)
    raise_on_error = _env_bool("REPUTATION_HTTP_RAISE_ERRORS", False)
    attempt = 0
    context = _ssl_context()

    while True:
        try:
            req = Request(url, headers=req_headers)
            with urlopen(req, timeout=timeout, context=context) as response:
                raw, truncated = _read_response(response, max_bytes)
            text = raw.decode("utf-8", errors="replace")
            if not truncated:
                _http_cache_set(cache_key, text)
            return text
        except HTTPError as exc:
            if exc.code in {429, 502, 503, 403}:
                _block_host(url)
            if attempt >= retries:
                return ""
            sleep_for = backoff * (2**attempt)
            attempt += 1
            if sleep_for > 0:
                time.sleep(sleep_for)
        except Exception as exc:
            if attempt >= retries:
                if raise_on_error:
                    raise
                logger.warning("http_get_text error for %s: %s", _safe_url_for_logs(url), exc)
                return ""
            sleep_for = backoff * (2**attempt)
            attempt += 1
            if sleep_for > 0:
                time.sleep(sleep_for)


def http_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    raw = http_get_text(url, headers=headers, timeout=timeout)
    if not raw or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if rss_debug_enabled():
            logger.debug("http_get_json decode failed for %s", _safe_url_for_logs(url))
        return {}


def build_url(base: str, params: dict[str, Any]) -> str:
    return f"{base}?{urlencode({k: v for k, v in params.items() if v is not None})}"


def parse_rss(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = SafeElementTree.fromstring(xml_text)
    except Exception as exc:
        if rss_debug_enabled():
            logger.debug("parse_rss failed: %s", exc)
        return []

    items: list[dict[str, Any]] = []
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            items.append(_parse_rss_item(item))
        return items

    ns = _get_ns(root)
    for entry in root.findall(f".//{ns}entry"):
        items.append(_parse_atom_entry(entry, ns))
    return items


def _parse_rss_item(item: ElementTree.Element) -> dict[str, Any]:
    return {
        "title": _text(item.find("title")),
        "link": _text(item.find("link")),
        "summary": _text(item.find("description")),
        "published": _text(item.find("pubDate")),
    }


def _parse_atom_entry(entry: ElementTree.Element, ns: str) -> dict[str, Any]:
    link_elem = entry.find(f"{ns}link")
    link = link_elem.attrib.get("href") if link_elem is not None else None
    return {
        "title": _text(entry.find(f"{ns}title")),
        "link": link,
        "summary": _text(entry.find(f"{ns}summary")) or _text(entry.find(f"{ns}content")),
        "published": _text(entry.find(f"{ns}updated")) or _text(entry.find(f"{ns}published")),
    }


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


def _text(elem: ElementTree.Element | None) -> str | None:
    if elem is None:
        return None
    if elem.text:
        return elem.text.strip()
    return None


def _get_ns(elem: ElementTree.Element) -> str:
    if elem.tag.startswith("{"):
        return elem.tag.split("}")[0] + "}"
    return ""


def _ssl_context() -> ssl.SSLContext | None:
    verify = os.getenv("REPUTATION_SSL_VERIFY", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    if not verify:
        # Cloud Run always has a trusted certificate store; allowing TLS verification bypass
        # in production is a footgun (MITM/data-tampering risk). Keep the toggle for local
        # troubleshooting only.
        if os.getenv("K_SERVICE"):
            logger.warning("REPUTATION_SSL_VERIFY=false ignored on Cloud Run (TLS verification enforced).")
            verify = True
        else:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _env_true(key: str) -> bool:
    return os.getenv(key, "false").strip().lower() in {"1", "true", "yes", "y", "on"}


def rss_debug_enabled() -> bool:
    return _env_true("REPUTATION_DEBUG_FEEDS") or _env_true("REPUTATION_LOG_DEBUG")


_STOPWORDS = {
    "a",
    "al",
    "and",
    "con",
    "de",
    "del",
    "el",
    "en",
    "for",
    "in",
    "la",
    "las",
    "los",
    "o",
    "of",
    "on",
    "or",
    "para",
    "por",
    "the",
    "to",
    "un",
    "una",
    "with",
    "y",
}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", " ", without_accents)
    return " ".join(cleaned.split())


def tokenize(text: str) -> list[str]:
    return normalize_text(text).split()


@dataclass(frozen=True)
class CompiledKeywords:
    tokens: list[list[str]]
    has_any: bool


def compile_keywords(keywords: Iterable[str]) -> CompiledKeywords:
    compiled: list[list[str]] = []
    seen_any = False
    for keyword in keywords:
        seen_any = True
        if not keyword:
            continue
        ktokens = [t for t in tokenize(keyword) if t not in _STOPWORDS and len(t) > 1]
        if ktokens:
            compiled.append(ktokens)
    return CompiledKeywords(tokens=compiled, has_any=seen_any)


def match_compiled(tokens: set[str], compiled: CompiledKeywords) -> bool:
    if not compiled.has_any:
        return True
    if not tokens:
        return False
    if not compiled.tokens:
        return False
    return any(all(token in tokens for token in ktokens) for ktokens in compiled.tokens)


def match_keywords(text: str | None, keywords: Iterable[str]) -> bool:
    if not keywords:
        return True
    if not text:
        return False
    tokens = set(tokenize(text))
    if not tokens:
        return False
    for keyword in keywords:
        if not keyword:
            continue
        ktokens = [t for t in tokenize(keyword) if t not in _STOPWORDS and len(t) > 1]
        if not ktokens:
            continue
        if all(token in tokens for token in ktokens):
            return True
    return False


def rss_source(value: dict[str, str] | str) -> tuple[str, dict[str, str]]:
    if isinstance(value, dict):
        url = value.get("url", "")
        meta = {k: v for k, v in value.items() if k != "url" and v}
    else:
        url = value
        meta = {}
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        raw_query = ""
        if qs.get("q"):
            raw_query = qs["q"][0]
        if raw_query and "query" not in meta:
            decoded = unquote_plus(raw_query)
            meta["query"] = decoded
            if "entity_hint" not in meta:
                quoted = re.findall(r'"([^"]+)"', decoded)
                if quoted:
                    meta["entity_hint"] = quoted[0]
    except Exception:
        pass
    return url, meta


def rss_is_query_feed(url: str) -> bool:
    if not url:
        return False
    url_lc = url.lower()
    return "news.google.com/rss/search" in url_lc or "google.com/alerts/feeds" in url_lc
