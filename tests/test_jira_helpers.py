"""Tests for small Jira adapter helpers."""

from __future__ import annotations

from datetime import date

import httpx

from bugresolutionradar.adapters import jira_adapter


def test_normalize_jira_base_url() -> None:
    assert (
        jira_adapter._normalize_jira_base_url("jira.example.com/secure/Dashboard.jspa")
        == "https://jira.example.com"
    )
    assert (
        jira_adapter._normalize_jira_base_url("https://jira.example.com/jira/secure/Dashboard.jspa")
        == "https://jira.example.com/jira"
    )
    assert jira_adapter._normalize_jira_base_url("https://jira.example.com/rest/api/2/search") == (
        "https://jira.example.com"
    )


def test_extract_error_detail() -> None:
    resp = httpx.Response(
        400,
        json={
            "errorMessages": ["Bad request"],
            "errors": {"jql": "invalid"},
        },
    )
    detail = jira_adapter._extract_jira_error_detail(resp)
    assert detail is not None
    assert "Bad request" in detail
    assert "jql" in detail


def test_discover_base_url_from_rest() -> None:
    url = "https://jira.example.com/jira/rest/api/2/search"
    assert jira_adapter._discover_base_url_from_rest_url(url) == "https://jira.example.com/jira"


def test_jira_date_parsing() -> None:
    assert jira_adapter._jira_date("2025-01-10T12:00:00.000+0000") == date(2025, 1, 10)
    assert jira_adapter._jira_date("2025-01-10") == date(2025, 1, 10)
    assert jira_adapter._jira_date("invalid") is None
