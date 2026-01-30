from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
import json
from typing import Any, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import ssl
import os
from xml.etree import ElementTree


def http_get_text(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> str:
    req_headers = {"User-Agent": "bbva-brr-reputation/0.1"}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    context = _ssl_context()
    with urlopen(req, timeout=timeout, context=context) as response:
        data = cast(bytes, response.read())
        return data.decode("utf-8")


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


def rss_debug_enabled() -> bool:
    return os.getenv("REPUTATION_DEBUG_FEEDS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
