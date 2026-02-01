from __future__ import annotations

import json
import os
import re
import ssl
import unicodedata
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote_plus, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


def http_get_text(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> str:
    req_headers = {"User-Agent": "global-overview-radar/0.1"}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    context = _ssl_context()
    with urlopen(req, timeout=timeout, context=context) as response:
        raw = response.read()
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def http_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    raw = http_get_text(url, headers=headers, timeout=timeout)
    return json.loads(raw)


def build_url(base: str, params: dict[str, Any]) -> str:
    return f"{base}?{urlencode({k: v for k, v in params.items() if v is not None})}"


def parse_rss(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
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
