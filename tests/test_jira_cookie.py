"""Tests for Jira cookie utilities."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from bugresolutionradar.utils.jira_cookie import (
    JiraCookieError,
    _cookie_header_from_jar,
    _domain_matches,
    extract_domain,
)


@dataclass(frozen=True)
class DummyCookie:
    name: str
    value: str
    domain: str | None = None


def test_extract_domain_accepts_url_and_host() -> None:
    assert extract_domain("https://jira.example.com/secure/Dashboard.jspa") == "jira.example.com"
    assert extract_domain("jira.example.com") == "jira.example.com"


def test_extract_domain_rejects_empty() -> None:
    with pytest.raises(JiraCookieError):
        extract_domain("")


def test_domain_matches_subdomains() -> None:
    assert _domain_matches(".example.com", "jira.example.com")
    assert _domain_matches("example.com", "jira.example.com")
    assert not _domain_matches("evil.com", "jira.example.com")


def test_cookie_header_from_jar_filters_domain() -> None:
    jar = [
        DummyCookie(name="a", value="1", domain=".example.com"),
        DummyCookie(name="b", value="2", domain="jira.example.com"),
        DummyCookie(name="c", value="3", domain="other.com"),
    ]
    header = _cookie_header_from_jar(jar, "jira.example.com")
    parts = {p.strip() for p in header.split(";")}
    assert "a=1" in parts
    assert "b=2" in parts
    assert "c=3" not in parts
