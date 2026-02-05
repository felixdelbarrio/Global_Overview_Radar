from __future__ import annotations

from datetime import date

import httpx

from bugresolutionradar.adapters import JiraAdapter, JiraConfig
from bugresolutionradar.domain.enums import Severity, Status


def test_jira_adapter_maps_issue_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rest/api/3/search"):
            payload = {
                "startAt": 0,
                "maxResults": 50,
                "total": 1,
                "issues": [
                    {
                        "key": "MEXBMI1-123",
                        "fields": {
                            "summary": "Login falla en iOS",
                            "status": {
                                "name": "Done",
                                "statusCategory": {"key": "done"},
                            },
                            "priority": {"name": "Highest"},
                            "created": "2025-01-10T12:00:00.000+0000",
                            "updated": "2025-01-12T09:00:00.000+0000",
                            "resolutiondate": "2025-01-12T09:00:00.000+0000",
                            "resolution": {"name": "Fixed"},
                            "components": [{"name": "Mobile"}],
                        },
                    }
                ],
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://jira.example", transport=transport)

    adapter = JiraAdapter(
        "jira",
        JiraConfig(
            base_url="https://jira.example",
            user_email="user@example.com",
            api_token="token",
            jql="project = MEXBMI1",
        ),
        client=client,
    )
    items = adapter.read()

    assert len(items) == 1
    item = items[0]
    assert item.source_id == "jira"
    assert item.source_key == "MEXBMI1-123"
    assert item.title == "Login falla en iOS"
    assert item.status == Status.CLOSED
    assert item.severity == Severity.CRITICAL
    assert item.opened_at == date(2025, 1, 10)
    assert item.updated_at == date(2025, 1, 12)
    assert item.closed_at == date(2025, 1, 12)
    assert item.product == "Mobile"
    assert item.resolution_type == "Fixed"


def test_jira_adapter_uses_filter_id_when_jql_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rest/api/3/filter/999"):
            return httpx.Response(200, json={"id": "999", "jql": "project = MEXBMI1"})
        if request.url.path.endswith("/rest/api/3/search"):
            payload = {
                "startAt": 0,
                "maxResults": 50,
                "total": 0,
                "issues": [],
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://jira.example", transport=transport)

    adapter = JiraAdapter(
        "jira",
        JiraConfig(
            base_url="https://jira.example",
            user_email="user@example.com",
            api_token="token",
            jql="",
            filter_id="999",
        ),
        client=client,
    )
    items = adapter.read()
    assert items == []


def test_jira_adapter_normalizes_ui_dashboard_url() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/rest/api/3/search"):
            payload = {
                "startAt": 0,
                "maxResults": 50,
                "total": 0,
                "issues": [],
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://jira.example", transport=transport)

    adapter = JiraAdapter(
        "jira",
        JiraConfig(
            base_url="https://jira.example/secure/Dashboard.jspa",
            user_email="user@example.com",
            api_token="token",
            jql="project = MEXBMI1",
        ),
        client=client,
    )
    adapter.read()

    assert requested_paths == ["/rest/api/3/search"]


def test_jira_adapter_preserves_context_path_when_base_url_includes_it() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/rest/api/3/search"):
            payload = {
                "startAt": 0,
                "maxResults": 50,
                "total": 0,
                "issues": [],
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://jira.example", transport=transport)

    adapter = JiraAdapter(
        "jira",
        JiraConfig(
            base_url="https://jira.example/jira/secure/Dashboard.jspa",
            user_email="user@example.com",
            api_token="token",
            jql="project = MEXBMI1",
        ),
        client=client,
    )
    adapter.read()

    assert requested_paths == ["/jira/rest/api/3/search"]


def test_jira_adapter_falls_back_to_jira_context_path_on_404() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path in {"/rest/api/3/search", "/rest/api/2/search"}:
            return httpx.Response(404, json={"error": "not found"})
        if request.url.path == "/jira/rest/api/3/search":
            payload = {
                "startAt": 0,
                "maxResults": 50,
                "total": 0,
                "issues": [],
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://jira.example", transport=transport)

    adapter = JiraAdapter(
        "jira",
        JiraConfig(
            base_url="https://jira.example",
            user_email="user@example.com",
            api_token="token",
            jql="project = MEXBMI1",
        ),
        client=client,
    )
    adapter.read()

    assert requested_paths == [
        "/rest/api/3/search",
        "/rest/api/2/search",
        "/jira/rest/api/3/search",
    ]
