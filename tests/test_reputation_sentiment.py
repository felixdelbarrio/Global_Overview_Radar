from __future__ import annotations

import json
from pathlib import Path

import pytest

from reputation.collectors.base import ReputationCollector
from reputation.models import ReputationItem
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


def test_ingest_service_forces_downdetector_as_negative(
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

    assert by_id["dd-1"].sentiment == "negative"
    assert by_id["dd-1"].signals.get("sentiment_score") == -1.0
    assert by_id["dd-1"].signals.get("sentiment_provider") == "source_rule"
    assert (
        by_id["dd-1"].signals.get("source_sentiment_rule")
        == "downdetector_always_negative"
    )
    assert by_id["news-1"].signals.get("source_sentiment_rule") is None


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
