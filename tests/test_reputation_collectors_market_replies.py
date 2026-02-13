from __future__ import annotations

import json

import pytest

from reputation.collectors.appstore import (
    _REPLY_SIGNATURE_PREFIX,
    _review_signature,
    AppStoreCollector,
    AppStoreScraperCollector,
)
from reputation.collectors.google_play import (
    _extract_reviews_from_html,
    _map_play_review,
)


def test_appstore_scraper_reads_serialized_server_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "data": {
            "items": [
                {
                    "id": "r1",
                    "title": "Muy mala",
                    "contents": "Se cae continuamente",
                    "rating": 1,
                    "reviewerName": "Ana",
                    "date": "2026-01-31T12:00:00Z",
                    "response": {
                        "contents": "Gracias por escribirnos",
                        "date": "2026-02-01T12:00:00Z",
                    },
                }
            ]
        }
    }
    html = (
        "<html><body>"
        '<script id="organization" type="application/ld+json">{"name":"App Store"}</script>'
        f'<script id="serialized-server-data" type="application/json">{json.dumps(payload)}</script>'
        "</body></html>"
    )
    monkeypatch.setattr(
        "reputation.collectors.appstore.http_get_text", lambda *_, **__: html
    )

    collector = AppStoreScraperCollector(
        country="es", app_id="1209986220", max_reviews=10
    )
    items = list(collector.collect())

    assert len(items) == 1
    signals = items[0].signals
    assert signals.get("has_reply") is True
    assert signals.get("reply_text") == "Gracias por escribirnos"
    assert signals.get("reply_at") == "2026-02-01T12:00:00+00:00"


def test_appstore_rss_enriches_replies_from_scraped_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPSTORE_REPLY_ENRICH_ENABLED", "true")
    collector = AppStoreCollector(country="es", app_id="1209986220", max_reviews=5)

    rss_entry = {
        "id": {"attributes": {"im:id": "r1"}},
        "im:rating": {"label": "1"},
        "updated": {"label": "2026-01-31T12:00:00Z"},
        "author": {"name": {"label": "Ana"}},
        "title": {"label": "Muy mala"},
        "content": {"label": "Se cae continuamente"},
    }

    monkeypatch.setattr(
        collector,
        "_fetch_page",
        lambda page: [rss_entry] if page == 1 else [],
    )
    monkeypatch.setattr(
        collector,
        "_fetch_scraped_reply_map",
        lambda: {
            "r1": {
                "text": "Gracias por escribirnos",
                "author": "Bankinter",
                "replied_at": "2026-02-01T12:00:00+00:00",
            }
        },
    )

    items = list(collector.collect())

    assert len(items) == 1
    signals = items[0].signals
    assert signals.get("has_reply") is True
    assert signals.get("reply_text") == "Gracias por escribirnos"
    assert signals.get("reply_author") == "Bankinter"


def test_appstore_rss_enriches_replies_with_signature_when_ids_do_not_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPSTORE_REPLY_ENRICH_ENABLED", "true")
    collector = AppStoreCollector(country="es", app_id="1209986220", max_reviews=5)

    rss_entry = {
        "id": {"attributes": {"im:id": "rss-r1"}},
        "im:rating": {"label": "1"},
        "updated": {"label": "2026-01-31T12:00:00Z"},
        "author": {"name": {"label": "Ana"}},
        "title": {"label": "Muy mala"},
        "content": {"label": "Se cae continuamente"},
    }
    signature = _review_signature(
        author="Ana",
        title="Muy mala",
        text="Se cae continuamente",
        published_at="2026-01-31T12:00:00Z",
    )
    assert signature is not None

    monkeypatch.setattr(
        collector,
        "_fetch_page",
        lambda page: [rss_entry] if page == 1 else [],
    )
    monkeypatch.setattr(
        collector,
        "_fetch_scraped_reply_map",
        lambda: {
            f"{_REPLY_SIGNATURE_PREFIX}{signature}": {
                "text": "Gracias por escribirnos",
                "author": "Bankinter",
                "replied_at": "2026-02-01T12:00:00+00:00",
            }
        },
    )

    items = list(collector.collect())

    assert len(items) == 1
    signals = items[0].signals
    assert signals.get("has_reply") is True
    assert signals.get("reply_text") == "Gracias por escribirnos"
    assert signals.get("reply_author") == "Bankinter"


def test_google_play_scraper_extracts_developer_reply_block() -> None:
    html = """
    <header class="c1bOId" data-review-id="abc"></header>
    <div class="X5PpBb">Usuario Uno</div>
    <span class="bp9Aid">5 de diciembre de 2025</span>
    <div aria-label="Valoración: 2 estrellas de cinco"></div>
    <div class="h3YV2d">La aplicacion falla y no abre</div>
    <div class="ocpBU">
      <div class="T6E0ze">
        <div class="I6j64d">Bankinter</div>
        <div class="I9Jtec">13 de mayo de 2024</div>
      </div>
      <div class="ras4vb"><div>Hola. Disculpa las molestias.</div></div>
    </div>
    """

    reviews = _extract_reviews_from_html(html, limit=1, language="es")

    assert len(reviews) == 1
    review = reviews[0]
    assert review.get("rating") == 2.0
    assert review.get("replyText") == "Hola. Disculpa las molestias."
    assert review.get("replyAuthor") == "Bankinter"
    assert review.get("replyDate") == "2024-05-13T00:00:00+00:00"

    item = _map_play_review(
        review,
        source="google_play",
        package_id="com.bankinter.empresas",
        country="ES",
        language="es",
        geo="España",
    )
    assert item is not None
    assert item.signals.get("has_reply") is True
    assert item.signals.get("reply_text") == "Hola. Disculpa las molestias."


def test_google_play_api_map_extracts_nested_developer_reply() -> None:
    review = {
        "id": "gp-api-1",
        "author_name": "Usuario Uno",
        "title": "No funciona",
        "content": "La app falla",
        "date": "2026-02-10T10:00:00Z",
        "reviewRating": {"value": "1"},
        "developerResponse": {
            "comment": "Gracias por avisar, estamos revisándolo.",
            "developer_name": "Acme Support",
            "lastModified": "2026-02-13T11:00:00Z",
        },
    }

    item = _map_play_review(
        review,
        source="google_play",
        package_id="com.acme.app",
        country="ES",
        language="es",
        geo="España",
    )

    assert item is not None
    assert item.author == "Usuario Uno"
    assert item.signals.get("rating") == "1"
    assert item.signals.get("has_reply") is True
    assert "Gracias por avisar" in str(item.signals.get("reply_text"))
    assert item.signals.get("reply_author") == "Acme Support"
