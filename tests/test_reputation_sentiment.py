from __future__ import annotations

import json
from pathlib import Path

import pytest

from reputation.collectors.base import ReputationCollector
from reputation.models import MarketRating, ReputationItem
from reputation.services.ingest_service import ReputationIngestService
from reputation.services.sentiment_service import ReputationSentimentService


def _service(
    monkeypatch: pytest.MonkeyPatch, *, llm_enabled: bool
) -> ReputationSentimentService:
    monkeypatch.setenv("LLM_ENABLED", "true" if llm_enabled else "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    cfg = {
        "models": {
            "llm_model": "gpt-5.2",
        },
        "llm": {
            "batch_size": 4,
        },
    }
    return ReputationSentimentService(cfg)


def test_non_client_item_defaults_to_neutral_when_llm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(monkeypatch, llm_enabled=False)
    item = ReputationItem(
        id="n1",
        source="news",
        title="Cargos inesperados",
        text="La app cobra comisiones.",
        signals={},
    )

    result = service.analyze_item(item)

    assert result.sentiment == "neutral"
    assert result.signals.get("sentiment_score") == 0.0
    assert result.signals.get("sentiment_provider") is None


def test_google_play_rating_uses_stars_and_skips_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(monkeypatch, llm_enabled=True)

    def _unexpected_call(*args: object, **kwargs: object) -> str:
        raise AssertionError("LLM no debe ejecutarse para items con estrellas")

    monkeypatch.setattr(service, "_send_llm_request", _unexpected_call)
    item = ReputationItem(
        id="gp1",
        source="google_play",
        title="Buenísima",
        text="Funciona muy bien",
        signals={"rating": 4.8},
    )

    result = service.analyze_item(item)

    assert result.sentiment == "positive"
    assert result.signals.get("sentiment_provider") == "stars"
    assert result.signals.get("client_sentiment") is True


@pytest.mark.parametrize(
    ("rating", "expected_label", "expected_score"),
    [
        (1.0, "negative", -1.0),
        (2.5, "neutral", 0.0),
        (5.0, "positive", 1.0),
    ],
)
def test_store_ratings_use_strict_sentiment_mapping(
    monkeypatch: pytest.MonkeyPatch,
    rating: float,
    expected_label: str,
    expected_score: float,
) -> None:
    service = _service(monkeypatch, llm_enabled=True)

    def _unexpected_call(*args: object, **kwargs: object) -> str:
        raise AssertionError("LLM no debe ejecutarse para items con estrellas")

    monkeypatch.setattr(service, "_send_llm_request", _unexpected_call)
    item = ReputationItem(
        id=f"gp-{rating}",
        source="google_play",
        title="Reseña",
        text="Contenido",
        signals={"rating": rating},
    )

    result = service.analyze_item(item)

    assert result.sentiment == expected_label
    assert result.signals.get("sentiment_score") == pytest.approx(expected_score)
    assert result.signals.get("sentiment_provider") == "stars"


def test_star_sentiment_extracts_score_field_for_store_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(monkeypatch, llm_enabled=True)

    def _unexpected_call(*args: object, **kwargs: object) -> str:
        raise AssertionError("LLM no debe ejecutarse para items con estrellas")

    monkeypatch.setattr(service, "_send_llm_request", _unexpected_call)
    item = ReputationItem(
        id="gp-score",
        source="google_play",
        title="Reseña",
        text="Contenido",
        signals={"score": "1"},
    )

    result = service.analyze_item(item)

    assert result.sentiment == "negative"
    assert result.signals.get("sentiment_score") == pytest.approx(-1.0)
    assert result.signals.get("sentiment_provider") == "stars"


def test_existing_star_classification_is_not_reprocessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(monkeypatch, llm_enabled=True)

    def _unexpected_call(*args: object, **kwargs: object) -> str:
        raise AssertionError(
            "LLM no debe ejecutarse para items ya clasificados por cliente"
        )

    monkeypatch.setattr(service, "_send_llm_request", _unexpected_call)
    item = ReputationItem(
        id="gp2",
        source="google_play",
        sentiment="neutral",
        signals={"sentiment_provider": "stars", "sentiment_score": 0.0},
    )

    result = service.analyze_item(item)

    assert result.sentiment == "neutral"
    assert result.signals.get("sentiment_provider") == "stars"
    assert result.signals.get("sentiment_score") == 0.0


def test_manual_sentiment_lock_is_never_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(monkeypatch, llm_enabled=True)

    def _mock_llm(
        payload_items: list[dict[str, object]], *_: object, **__: object
    ) -> str:
        assert [str(item.get("id")) for item in payload_items] == ["open"]
        return json.dumps(
            {
                "items": [
                    {
                        "id": "open",
                        "sentiment": "positive",
                        "signals": {"sentiment_score": 0.73},
                    }
                ]
            }
        )

    monkeypatch.setattr(service, "_send_llm_request", _mock_llm)

    locked = ReputationItem(
        id="locked",
        source="news",
        sentiment="negative",
        title="Ignorado",
        text="No debe cambiar",
        signals={
            "manual_sentiment": True,
            "sentiment_locked": True,
            "sentiment_provider": "manual_override",
            "sentiment_score": -0.9,
        },
    )
    open_item = ReputationItem(
        id="open",
        source="news",
        title="Mejora del servicio",
        text="Menos incidencias",
        signals={},
    )

    results = service.analyze_items([locked, open_item])
    by_id = {item.id: item for item in results}

    assert by_id["locked"].sentiment == "negative"
    assert by_id["locked"].signals.get("sentiment_provider") == "manual_override"
    assert by_id["locked"].signals.get("sentiment_score") == -0.9

    assert by_id["open"].sentiment == "positive"
    assert by_id["open"].signals.get("sentiment_provider") == "openai"


def test_llm_failure_falls_back_to_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(monkeypatch, llm_enabled=True)

    def _llm_failure(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(service, "_send_llm_request", _llm_failure)
    item = ReputationItem(
        id="n2",
        source="news",
        title="Título con sesgo",
        text="Texto ambiguo",
        signals={},
    )

    result = service.analyze_item(item)

    assert result.sentiment == "neutral"
    assert result.signals.get("sentiment_score") == 0.0
    assert result.signals.get("sentiment_provider") is None


def test_ingest_service_applies_manual_override_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import reputation.config as rep_config

    overrides_path = tmp_path / "reputation_overrides.json"
    overrides_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-01-01T00:00:00+00:00",
                "items": {
                    "n3": {"sentiment": "negative"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rep_config.settings, "overrides_path", overrides_path)

    service = ReputationIngestService()
    items = [
        ReputationItem(id="n3", source="news", title="x", text="y", signals={}),
        ReputationItem(id="n4", source="news", title="x", text="y", signals={}),
    ]

    service._lock_manual_sentiment_items(items)

    assert items[0].sentiment == "negative"
    assert items[0].signals.get("sentiment_provider") == "manual_override"
    assert items[0].signals.get("sentiment_locked") is True
    assert items[1].sentiment is None


def test_ingest_service_ignores_manual_override_for_market_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import reputation.config as rep_config

    overrides_path = tmp_path / "reputation_overrides.json"
    overrides_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-01-01T00:00:00+00:00",
                "items": {
                    "market-1": {"sentiment": "positive"},
                    "news-1": {"sentiment": "negative"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rep_config.settings, "overrides_path", overrides_path)

    service = ReputationIngestService()
    items = [
        ReputationItem(
            id="market-1",
            source="google_play",
            title="x",
            text="y",
            signals={"rating": 1},
        ),
        ReputationItem(id="news-1", source="news", title="x", text="y", signals={}),
    ]

    service._lock_manual_sentiment_items(items)

    assert items[0].sentiment is None
    assert items[0].signals.get("sentiment_provider") is None
    assert items[0].signals.get("sentiment_locked") is None
    assert items[1].sentiment == "negative"
    assert items[1].signals.get("sentiment_provider") == "manual_override"
    assert items[1].signals.get("sentiment_locked") is True


def test_ingest_service_defaults_downdetector_to_neutral_without_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")
    service = ReputationIngestService()
    items = [
        ReputationItem(
            id="dd-1",
            source="downdetector",
            title="Incidencia",
            text="Servicio fuera de línea",
            sentiment="neutral",
            signals={"sentiment_score": 0.0},
        ),
        ReputationItem(
            id="news-1",
            source="news",
            title="Nota",
            text="Contenido general",
            sentiment="neutral",
            signals={},
        ),
    ]

    result = service._apply_sentiment({}, items, existing=None, notes=[])
    by_id = {item.id: item for item in result}

    assert by_id["dd-1"].sentiment == "neutral"
    assert by_id["dd-1"].signals.get("sentiment_score") == 0.0
    assert by_id["dd-1"].signals.get("sentiment_provider") == "source_rule"
    assert (
        by_id["dd-1"].signals.get("source_sentiment_rule")
        == "downdetector_default_neutral"
    )
    assert by_id["news-1"].signals.get("source_sentiment_rule") is None


def test_ingest_service_keeps_llm_sentiment_for_downdetector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    service = ReputationIngestService()
    items = [
        ReputationItem(
            id="dd-llm",
            source="downdetector",
            title="Incidencia",
            text="Servicio fuera de línea",
            sentiment="negative",
            signals={
                "sentiment_score": -0.72,
                "sentiment_provider": "openai",
                "sentiment_model": "gpt-5.2",
            },
        )
    ]

    service._apply_source_sentiment_rules(items)

    assert items[0].sentiment == "negative"
    assert items[0].signals.get("sentiment_score") == -0.72
    assert items[0].signals.get("sentiment_provider") == "openai"
    assert items[0].signals.get("source_sentiment_rule") is None


def test_ingest_service_recomputes_store_sentiment_even_for_existing_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")
    service = ReputationIngestService()
    existing = [
        ReputationItem(
            id="gp-existing",
            source="google_play",
            title="Antes",
            text="",
            sentiment="neutral",
            signals={
                "rating": 1,
                "sentiment_provider": "stars",
                "sentiment_score": 0.0,
            },
        )
    ]
    incoming = [
        ReputationItem(
            id="gp-existing",
            source="google_play",
            title="Ahora",
            text="",
            signals={"rating": 1},
        )
    ]

    updated = service._apply_sentiment({}, incoming, existing=existing, notes=[])
    merged = service._merge_items(existing, updated)
    by_id = {item.id: item for item in merged}

    assert by_id["gp-existing"].sentiment == "negative"
    assert by_id["gp-existing"].signals.get("sentiment_provider") == "stars"
    assert by_id["gp-existing"].signals.get("sentiment_score") == pytest.approx(-1.0)


def test_apply_star_sentiment_fast_sets_store_sentiment() -> None:
    item = ReputationItem(
        id="gp-fast",
        source="google_play",
        title="Resena",
        text="Contenido",
        signals={"rating": 4.7},
    )

    changed = ReputationIngestService._apply_star_sentiment_fast(item)

    assert changed is True
    assert item.sentiment == "positive"
    assert item.signals.get("sentiment_provider") == "stars"
    assert item.signals.get("client_sentiment") is True
    assert item.signals.get("sentiment_score") == pytest.approx(0.88)


def test_apply_star_sentiment_fast_respects_locked_sentiment() -> None:
    item = ReputationItem(
        id="gp-fast-locked",
        source="google_play",
        title="Resena",
        text="Contenido",
        sentiment="neutral",
        signals={
            "rating": 1.0,
            "sentiment_provider": "manual_override",
            "sentiment_locked": True,
            "sentiment_score": 0.0,
        },
    )

    changed = ReputationIngestService._apply_star_sentiment_fast(item)

    assert changed is False
    assert item.sentiment == "neutral"
    assert item.signals.get("sentiment_provider") == "manual_override"
    assert item.signals.get("sentiment_score") == 0.0


def test_apply_sentiment_does_not_init_service_when_existing_items_are_star_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reputation.services.ingest_service as ingest_service

    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.delenv("REPUTATION_TRANSLATE_TARGET", raising=False)

    class _ShouldNotInit:
        def __init__(self, *_: object, **__: object) -> None:
            raise AssertionError("ReputationSentimentService no debe inicializarse")

    monkeypatch.setattr(ingest_service, "ReputationSentimentService", _ShouldNotInit)

    service = ReputationIngestService()
    existing = [
        ReputationItem(
            id="gp-existing-only",
            source="google_play",
            title="Antes",
            text="",
            signals={"rating": 4.8},
        )
    ]
    incoming = [
        ReputationItem(
            id="gp-existing-only",
            source="google_play",
            title="Ahora",
            text="",
            signals={"rating": 4.8},
        )
    ]

    result = service._apply_sentiment({}, incoming, existing=existing, notes=[])

    assert result[0].sentiment == "positive"
    assert result[0].signals.get("sentiment_provider") == "stars"


def test_apply_sentiment_does_not_init_service_when_no_existing_star_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reputation.services.ingest_service as ingest_service

    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.delenv("REPUTATION_TRANSLATE_TARGET", raising=False)

    class _ShouldNotInit:
        def __init__(self, *_: object, **__: object) -> None:
            raise AssertionError("ReputationSentimentService no debe inicializarse")

    monkeypatch.setattr(ingest_service, "ReputationSentimentService", _ShouldNotInit)

    service = ReputationIngestService()
    incoming = [
        ReputationItem(
            id="gp-no-existing-only",
            source="google_play",
            title="Ahora",
            text="",
            signals={"rating": 1.0},
        )
    ]

    result = service._apply_sentiment({}, incoming, existing=None, notes=[])

    assert result[0].sentiment == "negative"
    assert result[0].signals.get("sentiment_provider") == "stars"


def test_tokens_match_keyword_reuses_compiled_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reputation.services.ingest_service as ingest_service

    ingest_service._compile_single_keyword.cache_clear()
    original_compile = ingest_service.compile_keywords
    calls = {"count": 0}

    def _spy_compile(keywords: list[str]) -> object:
        calls["count"] += 1
        return original_compile(keywords)

    monkeypatch.setattr(ingest_service, "compile_keywords", _spy_compile)

    tokens = {"bbva"}
    assert ReputationIngestService._tokens_match_keyword(tokens, "bbva") is True
    assert ReputationIngestService._tokens_match_keyword(tokens, "bbva") is True
    assert calls["count"] == 1
    ingest_service._compile_single_keyword.cache_clear()


def test_collector_batch_returns_list_without_copying() -> None:
    class _ListCollector(ReputationCollector):
        def __init__(self, source_name: str, payload: list[ReputationItem]) -> None:
            self.source_name = source_name
            self._payload = payload

        def collect(self) -> list[ReputationItem]:
            return self._payload

    payload = [
        ReputationItem(id="batch-1", source="news", title="x", text="y", signals={})
    ]
    collector = _ListCollector("news", payload)

    batch = ReputationIngestService._collector_batch(collector)

    assert batch is payload


def test_build_google_play_collector_sets_progress_name() -> None:
    collector = ReputationIngestService._build_google_play_collector(
        api_enabled=False,
        endpoint="",
        api_key=None,
        api_key_param="key",
        package_id="com.example.app",
        country="ES",
        language="es",
        max_reviews=10,
        scrape_timeout=5,
        geo="España",
    )

    assert collector is not None
    assert collector.source_name == "google_play"
    assert (
        getattr(collector, "progress_name", "")
        == "google_play:com.example.app:ES/es:España"
    )


def test_build_collectors_google_play_applies_core_only_and_dedupe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLAY_API_ENABLED", "false")
    monkeypatch.delenv("GOOGLE_PLAY_PACKAGE_IDS", raising=False)
    monkeypatch.setenv("GOOGLE_PLAY_DEFAULT_COUNTRY", "ES")
    monkeypatch.setenv("GOOGLE_PLAY_DEFAULT_LANGUAGE", "es")

    cfg = {
        "actor_principal": "BBVA",
        "keywords": ["bbva"],
        "google_play": {
            "core_only": True,
            "package_ids": ["pkg.bbva", "pkg.bbva.dup", "pkg.bbva"],
            "package_ids_by_geo": {
                "España": [
                    "pkg.santander.es",
                    "pkg.santander.es.dup",
                    "pkg.santander.es",
                ],
                "México": ["pkg.santander.mx", "pkg.santander.mx"],
            },
            "geo_to_gl": {"España": "ES", "México": "MX"},
            "geo_to_hl": {"España": "es", "México": "es-419"},
            "package_id_to_actor": {
                "pkg.bbva": "BBVA",
                "pkg.bbva.dup": "BBVA",
                "pkg.santander.es": "Santander",
                "pkg.santander.es.dup": "Santander",
                "pkg.santander.mx": "Santander",
            },
        },
    }

    service = ReputationIngestService()
    collectors, notes = service._build_collectors(cfg, ["google_play"])

    tuples = {
        (
            getattr(collector, "_package_id", ""),
            getattr(collector, "_country", ""),
            getattr(collector, "_language", ""),
            getattr(collector, "_geo", None),
        )
        for collector in collectors
    }

    assert len(collectors) == 3
    assert ("pkg.bbva", "ES", "es", None) in tuples
    assert ("pkg.santander.es", "ES", "es", "España") in tuples
    assert ("pkg.santander.mx", "MX", "es-419", "México") in tuples
    assert any("google_play: skipped collectors" in note for note in notes)


def test_build_collectors_google_play_uses_scraper_when_api_endpoint_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_PLAY_API_ENABLED", "true")
    monkeypatch.delenv("GOOGLE_PLAY_API_ENDPOINT", raising=False)
    monkeypatch.setenv("GOOGLE_PLAY_DEFAULT_COUNTRY", "ES")
    monkeypatch.setenv("GOOGLE_PLAY_DEFAULT_LANGUAGE", "es")

    cfg = {
        "actor_principal": "BBVA",
        "keywords": ["bbva"],
        "google_play": {
            "package_ids": ["pkg.bbva"],
        },
    }

    service = ReputationIngestService()
    collectors, notes = service._build_collectors(cfg, ["google_play"])

    assert len(collectors) == 1
    assert getattr(collectors[0], "_package_id", "") == "pkg.bbva"
    assert any(
        "missing GOOGLE_PLAY_API_ENDPOINT (using scraper fallback)" in note
        for note in notes
    )


def test_build_collectors_appstore_applies_core_only_and_dedupe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPSTORE_API_ENABLED", "false")
    monkeypatch.setenv("APPSTORE_COUNTRY", "es")
    monkeypatch.delenv("APPSTORE_CORE_ONLY", raising=False)

    cfg = {
        "actor_principal": "BBVA",
        "keywords": ["bbva"],
        "appstore": {
            "core_only": True,
            "app_ids": ["app.bbva", "app.bbva.dup", "app.bbva"],
            "app_ids_by_geo": {
                "España": [
                    "app.santander.es",
                    "app.santander.es.dup",
                    "app.santander.es",
                ],
                "México": ["app.santander.mx", "app.santander.mx"],
            },
            "country_by_geo": {"España": "es", "México": "mx"},
            "app_id_to_actor": {
                "app.bbva": "BBVA",
                "app.bbva.dup": "BBVA",
                "app.santander.es": "Santander",
                "app.santander.es.dup": "Santander",
                "app.santander.mx": "Santander",
            },
        },
    }

    service = ReputationIngestService()
    collectors, notes = service._build_collectors(cfg, ["appstore"])

    tuples = {
        (
            getattr(collector, "_app_id", ""),
            getattr(collector, "_country", ""),
            getattr(collector, "_geo", None),
        )
        for collector in collectors
    }

    assert len(collectors) == 3
    assert ("app.bbva", "es", None) in tuples
    assert ("app.santander.es", "es", "España") in tuples
    assert ("app.santander.mx", "mx", "México") in tuples
    assert any("appstore: skipped collectors" in note for note in notes)


def test_collect_items_google_play_failover_uses_secondary_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "reputation.collectors.google_play.GooglePlayScraperCollector.collect",
        lambda self: [],
    )
    monkeypatch.setattr(
        "reputation.collectors.google_play.GooglePlayApiCollector.collect",
        lambda self: [
            ReputationItem(id="gp-fallback-1", source="google_play", text="ok")
        ],
    )

    collector = ReputationIngestService._build_google_play_collector(
        api_enabled=False,
        endpoint="https://collector.example/google-play",
        api_key=None,
        api_key_param="key",
        package_id="pkg.bbva",
        country="ES",
        language="es",
        max_reviews=10,
        scrape_timeout=5,
        failover_enabled=True,
        failover_min_reviews=1,
        geo="España",
    )

    notes: list[str] = []
    items = ReputationIngestService._collect_items([collector], notes)

    assert len(items) == 1
    assert items[0].id == "gp-fallback-1"
    assert any("google_play" in note and "failover" in note for note in notes)


def test_collect_items_appstore_failover_uses_secondary_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "reputation.collectors.appstore.AppStoreScraperCollector.collect",
        lambda self: [],
    )
    monkeypatch.setattr(
        "reputation.collectors.appstore.AppStoreCollector.collect",
        lambda self: [ReputationItem(id="as-fallback-1", source="appstore", text="ok")],
    )

    collector = ReputationIngestService._build_appstore_collector(
        api_enabled=False,
        country="es",
        app_id="12345",
        max_reviews=10,
        scrape_timeout=5,
        failover_enabled=True,
        failover_min_reviews=1,
        geo="España",
    )

    notes: list[str] = []
    items = ReputationIngestService._collect_items([collector], notes)

    assert len(items) == 1
    assert items[0].id == "as-fallback-1"
    assert any("appstore" in note and "failover" in note for note in notes)


def test_merge_items_backfills_author_and_reply_signals() -> None:
    existing = ReputationItem(
        id="merge-1",
        source="google_play",
        sentiment="negative",
        signals={"reply_text": "Gracias"},
    )
    incoming = ReputationItem(
        id="merge-1",
        source="google_play",
        author="Cliente Uno",
        collected_at=None,
        signals={"reply_text": None, "reply_author": "Acme Support"},
    )

    merged = ReputationIngestService._merge_items([existing], [incoming])

    assert len(merged) == 1
    assert merged[0].author == "Cliente Uno"
    assert merged[0].signals.get("reply_text") == "Gracias"
    assert merged[0].signals.get("reply_author") == "Acme Support"


def test_ingest_service_extracts_publisher_from_google_news_metadata() -> None:
    item = ReputationItem(
        id="news-1",
        source="news",
        url="https://news.google.com/rss/articles/abc?oc=5",
        title=(
            "Torres y Genç perciben un 3% menos de remuneración en 2025 "
            "pese al beneficio récord de BBVA - eleconomista.es"
        ),
        text=(
            '<a href="https://news.google.com/rss/articles/abc?oc=5" target="_blank">'
            "Torres y Genç perciben un 3% menos de remuneración en 2025 "
            "pese al beneficio récord de BBVA</a>&nbsp;&nbsp;"
            '<font color="#6f6f6f">eleconomista.es</font>'
        ),
        signals={"source": "Google News"},
    )

    ReputationIngestService._apply_publisher_metadata([item], notes=[])

    assert item.signals.get("publisher_domain") == "eleconomista.es"
    assert item.signals.get("publisher_name") == "eleconomista.es"


def test_ingest_service_extracts_publisher_from_direct_url() -> None:
    item = ReputationItem(
        id="news-2",
        source="news",
        url="https://www.cantabriaeconomica.com/empresa/rankia-awards-2025/",
        title="BBVA, Trade Republic, Sabadell... lideran los Rankia Awards 2025",
        text="Detalle de noticia",
        signals={},
    )

    ReputationIngestService._apply_publisher_metadata([item], notes=[])

    assert item.signals.get("publisher_domain") == "cantabriaeconomica.com"
    assert item.signals.get("publisher_name") == "cantabriaeconomica.com"


def test_apply_geo_hints_prefers_publisher_country_tld() -> None:
    cfg = {
        "geografias": ["España", "México"],
        "geografias_aliases": {
            "España": ["Spain", "ES"],
            "México": ["Mexico", "MX"],
        },
    }
    item = ReputationItem(
        id="geo-pub-1",
        source="news",
        geo="España",
        title="BBVA y AMAV acuerdan apoyo financiero y digital para agencias de viajes",
        signals={"publisher_domain": "expansion.com.mx"},
    )

    result = ReputationIngestService._apply_geo_hints(cfg, [item])

    assert result[0].geo == "México"
    assert result[0].signals.get("geo_source") == "publisher"


def test_apply_geo_hints_matches_publisher_subdomain_from_site_sources_map() -> None:
    cfg = {
        "geografias": ["España", "México"],
        "geografias_aliases": {
            "España": ["Spain", "ES"],
            "México": ["Mexico", "MX"],
        },
        "news": {
            "site_sources_by_geo": {
                "España": {"press": ["expansion.com"]},
                "México": {"press": ["ovaciones.com"]},
            }
        },
    }
    item = ReputationItem(
        id="geo-pub-map-1",
        source="news",
        geo="España",
        title="BBVA amplía operaciones",
        signals={"publisher_domain": "rss.ovaciones.com"},
    )

    result = ReputationIngestService._apply_geo_hints(cfg, [item])

    assert result[0].geo == "México"
    assert result[0].signals.get("geo_source") == "publisher"


def test_apply_geo_hints_ignores_ambiguous_site_source_domain() -> None:
    cfg = {
        "geografias": ["España", "México"],
        "geografias_aliases": {
            "España": ["Spain", "ES"],
            "México": ["Mexico", "MX"],
        },
        "news": {
            "site_sources_by_geo": {
                "España": {"press": ["reuters.com"]},
                "México": {"press": ["reuters.com"]},
            }
        },
    }
    item = ReputationItem(
        id="geo-ambiguous-domain-1",
        source="news",
        geo="México",
        title="BBVA acelera su agenda digital",
        url="https://www.reuters.com/world/europe/bbva-test-story",
        signals={},
    )

    result = ReputationIngestService._apply_geo_hints(cfg, [item])

    assert result[0].geo == "México"
    assert result[0].signals.get("geo_source") is None


def test_apply_geo_hints_detects_geo_with_html_and_url_encoding() -> None:
    cfg = {
        "geografias": ["España", "México"],
        "geografias_aliases": {
            "España": ["Spain", "ES"],
            "México": ["Mexico", "MX"],
        },
    }
    item = ReputationItem(
        id="geo-encoded-1",
        source="news",
        geo="España",
        title="BBVA M%C3%A9xico y AMAV firman acuerdo",
        text="<p>BBVA M&eacute;xico refuerza su estrategia.</p>",
        signals={},
    )

    result = ReputationIngestService._apply_geo_hints(cfg, [item])

    assert result[0].geo == "México"
    assert result[0].signals.get("geo_source") == "content"


def test_filter_noise_items_skips_tokenization_for_irrelevant_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = {
        "require_actor_sources": ["news"],
        "require_context_sources": ["news"],
        "noise_filter_sources": ["news"],
        "segment_terms": ["banco"],
        "noise_terms": ["deporte"],
    }
    item = ReputationItem(
        id="noise-skip-1",
        source="appstore",
        title="Aplicación estable",
        text="Actualización semanal",
        signals={},
    )
    calls = {"count": 0}
    original = ReputationIngestService._text_tokens

    def _spy_text_tokens(text: str) -> set[str]:
        calls["count"] += 1
        return original(text)

    monkeypatch.setattr(
        ReputationIngestService,
        "_text_tokens",
        staticmethod(_spy_text_tokens),
    )

    result = ReputationIngestService._filter_noise_items(cfg, [item], notes=[])

    assert len(result) == 1
    assert result[0].id == item.id
    assert calls["count"] == 0


def test_filter_noise_items_still_drops_noise_without_context_match() -> None:
    cfg = {
        "require_actor_sources": ["news"],
        "noise_filter_sources": ["news"],
        "segment_terms": ["banco"],
        "noise_terms": ["deporte"],
    }
    item = ReputationItem(
        id="noise-drop-1",
        source="news",
        actor="BBVA",
        title="BBVA patrocina evento de deporte",
        text="Resumen deportivo sin contexto bancario",
        signals={"actors": ["BBVA"]},
    )

    result = ReputationIngestService._filter_noise_items(cfg, [item], notes=[])

    assert result == []


def test_apply_geo_hints_does_not_match_short_alias_inside_words() -> None:
    cfg = {
        "geografias": ["España", "México"],
        "geografias_aliases": {
            "España": ["ES"],
            "México": ["MX"],
        },
    }
    item = ReputationItem(
        id="geo-short-alias-1",
        source="news",
        geo="México",
        title="Clientes satisfechos con nueva funcionalidad",
        text="Reporte semanal del equipo de producto",
        signals={},
    )

    result = ReputationIngestService._apply_geo_hints(cfg, [item])

    assert result[0].geo == "México"
    assert result[0].signals.get("geo_source") is None


def test_apply_geo_hints_prefers_title_geo_when_body_conflicts() -> None:
    cfg = {
        "geografias": ["España", "México"],
        "geografias_aliases": {
            "España": ["Spain", "ES"],
            "México": ["Mexico", "MX"],
        },
    }
    item = ReputationItem(
        id="geo-title-priority-1",
        source="news",
        title="BBVA México anuncia nuevo acuerdo financiero",
        text="Analistas en España valoran el impacto del anuncio.",
        signals={},
    )

    result = ReputationIngestService._apply_geo_hints(cfg, [item])

    assert result[0].geo == "México"
    assert result[0].signals.get("geo_source") == "content"


def test_round_robin_preserves_bucket_order() -> None:
    ordered = ReputationIngestService._round_robin(
        [
            {"geo": "ES", "id": "es-1"},
            {"geo": "ES", "id": "es-2"},
            {"geo": "MX", "id": "mx-1"},
            {"geo": "MX", "id": "mx-2"},
            {"geo": "CO", "id": "co-1"},
        ],
        "geo",
    )

    assert [item["id"] for item in ordered] == ["es-1", "mx-1", "co-1", "es-2", "mx-2"]


def test_merge_items_accepts_publisher_geo_override() -> None:
    existing = ReputationItem(
        id="merge-geo-1",
        source="news",
        geo="España",
        signals={},
    )
    incoming = ReputationItem(
        id="merge-geo-1",
        source="news",
        geo="México",
        signals={"geo_source": "publisher"},
    )

    merged = ReputationIngestService._merge_items([existing], [incoming])

    assert merged[0].geo == "México"


def test_merge_market_ratings_with_fallback_reuses_missing_keys() -> None:
    existing = [
        MarketRating(
            source="appstore",
            actor="BBVA",
            geo="España",
            app_id="app-1",
            rating=3.5,
            rating_count=100,
        ),
        MarketRating(
            source="google_play",
            actor="BBVA",
            geo="España",
            package_id="pkg-1",
            rating=4.2,
            rating_count=200,
        ),
    ]
    latest = [
        MarketRating(
            source="appstore",
            actor="BBVA",
            geo="España",
            app_id="app-1",
            rating=3.7,
            rating_count=130,
        ),
    ]

    merged, reused = ReputationIngestService._merge_market_ratings_with_fallback(
        existing,
        latest,
    )

    assert reused == 1
    assert len(merged) == 2
    # App Store keeps the latest value.
    assert any(
        entry.source == "appstore" and abs(entry.rating - 3.7) < 0.0001
        for entry in merged
    )
    # Google Play is reused from previous cache when missing in latest.
    assert any(
        entry.source == "google_play" and abs(entry.rating - 4.2) < 0.0001
        for entry in merged
    )


def test_merge_market_ratings_with_fallback_uses_latest_when_present() -> None:
    existing = [
        MarketRating(
            source="appstore",
            actor="BBVA",
            geo="España",
            app_id="app-1",
            rating=3.1,
            rating_count=90,
        )
    ]
    latest = [
        MarketRating(
            source="appstore",
            actor="BBVA",
            geo="España",
            app_id="app-1",
            rating=3.9,
            rating_count=150,
        )
    ]

    merged, reused = ReputationIngestService._merge_market_ratings_with_fallback(
        existing,
        latest,
    )

    assert reused == 0
    assert len(merged) == 1
    assert abs(merged[0].rating - 3.9) < 0.0001


def test_enforce_market_rating_assignment_reconciles_actor_geo_and_source() -> None:
    cfg = {
        "geografias": ["España"],
        "geografias_aliases": {"España": ["ES", "Espana"]},
        "actor_principal": {"BBVA": ["BBVA Empresas"]},
        "actor_principal_aliases": {"BBVA": ["BBVA Bank"]},
        "appstore": {"app_id_to_actor": {"app-1": "BBVA"}},
        "google_play": {"package_id_to_actor": {"pkg-1": "Santander"}},
    }
    ratings = [
        MarketRating(
            source="appstore",
            actor="BBVA Bank",
            geo="ES",
            app_id="app-1",
            rating=4.2,
            rating_count=120,
        ),
        MarketRating(
            source="googleplay",
            actor="BBVA",
            geo="Espana",
            package_id="pkg-1",
            rating=3.6,
            rating_count=230,
        ),
    ]
    notes: list[str] = []

    result = ReputationIngestService._enforce_market_rating_assignment(
        cfg, ratings, notes
    )

    assert len(result) == 2
    appstore = next(entry for entry in result if entry.source == "appstore")
    google_play = next(entry for entry in result if entry.source == "google_play")
    assert appstore.actor == "BBVA"
    assert google_play.actor == "Santander"
    assert appstore.geo == "España"
    assert google_play.geo == "España"
    assert any("actor_reassigned" in note for note in notes)
    assert any("geo_normalized" in note for note in notes)


def test_enforce_market_rating_assignment_deduplicates_by_identity() -> None:
    cfg = {
        "geografias": ["España"],
        "actor_principal": {"BBVA": ["BBVA Empresas"]},
        "actor_principal_aliases": {"BBVA": ["BBVA Bank"]},
        "appstore": {"app_id_to_actor": {"app-1": "BBVA"}},
    }
    ratings = [
        MarketRating(
            source="appstore",
            actor="BBVA Bank",
            geo="España",
            app_id="app-1",
            rating=3.1,
            rating_count=90,
        ),
        MarketRating(
            source="appstore",
            actor="BBVA",
            geo="España",
            app_id="app-1",
            rating=4.0,
            rating_count=180,
        ),
    ]
    notes: list[str] = []

    result = ReputationIngestService._enforce_market_rating_assignment(
        cfg, ratings, notes
    )

    assert len(result) == 1
    assert result[0].actor == "BBVA"
    assert abs(result[0].rating - 4.0) < 0.0001
    assert result[0].rating_count == 180
