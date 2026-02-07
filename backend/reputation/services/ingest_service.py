from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional, Sequence, cast
from urllib.parse import quote_plus, urlparse

from reputation.actors import (
    actor_principal_canonicals,
    actor_principal_terms,
    build_actor_alias_map,
    build_actor_aliases_by_canonical,
    canonicalize_actor,
    primary_actor_info,
)
from reputation.collectors.appstore import AppStoreCollector, AppStoreScraperCollector
from reputation.collectors.base import ReputationCollector
from reputation.collectors.blogs import BlogsCollector
from reputation.collectors.downdetector import DowndetectorCollector
from reputation.collectors.forums import ForumsCollector
from reputation.collectors.gdelt import GdeltCollector
from reputation.collectors.google_play import (
    GooglePlayApiCollector,
    GooglePlayScraperCollector,
)
from reputation.collectors.google_reviews import GoogleReviewsCollector
from reputation.collectors.guardian import GuardianCollector
from reputation.collectors.news import NewsCollector
from reputation.collectors.newsapi import NewsApiCollector
from reputation.collectors.reddit import RedditCollector
from reputation.collectors.trustpilot import TrustpilotCollector
from reputation.collectors.twitter import TwitterCollector
from reputation.collectors.utils import (
    http_get_json,
    http_get_text,
    match_keywords,
    normalize_text,
)
from reputation.collectors.youtube import YouTubeCollector
from reputation.config import (
    compute_config_hash,
    effective_ttl_hours,
    load_business_config,
    reload_reputation_settings,
    settings,
)
from reputation.logging_utils import get_logger
from reputation.models import (
    MarketRating,
    ReputationCacheDocument,
    ReputationCacheStats,
    ReputationItem,
)
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.services.sentiment_service import ReputationSentimentService

logger = get_logger(__name__)
ProgressCallback = Callable[[str, int, Optional[dict[str, Any]]], None]
CollectorProgress = Callable[[int, int, str], None]
DEFAULT_RSS_URL_LIMITS = {
    "NEWS_MAX_RSS_URLS": 300,
    "FORUMS_MAX_RSS_URLS": 300,
    "BLOGS_MAX_RSS_URLS": 300,
    "TRUSTPILOT_MAX_RSS_URLS": 300,
    "DOWNDETECTOR_MAX_RSS_URLS": 300,
}
DEFAULT_NEWS_RSS_LIMITS = {
    "max_total": 1200,
    "max_per_geo": 220,
    "max_per_entity": 40,
}
_GEO_COUNTRY_HINTS = {
    "espana": "es",
    "españa": "es",
    "spain": "es",
    "mexico": "mx",
    "méxico": "mx",
    "peru": "pe",
    "peru ": "pe",
    "perú": "pe",
    "colombia": "co",
    "argentina": "ar",
    "turquia": "tr",
    "turquía": "tr",
    "turkey": "tr",
    "global": "us",
    "world": "us",
    "estados unidos": "us",
    "united states": "us",
    "usa": "us",
}
_GOOGLE_PLAY_LOCALE_HINTS = {
    "es": ("ES", "es"),
    "mx": ("MX", "es-419"),
    "pe": ("PE", "es-419"),
    "co": ("CO", "es-419"),
    "ar": ("AR", "es-419"),
    "tr": ("TR", "tr"),
    "us": ("US", "en"),
}


def _primary_actor_canonical(cfg: dict[str, Any]) -> str:
    info = primary_actor_info(cfg)
    if not info:
        return ""
    canonical = info.get("canonical")
    return canonical.strip() if isinstance(canonical, str) else ""


def _guess_country_code(geo: str | None) -> str:
    if not geo:
        return ""
    normalized = normalize_text(geo)
    return _GEO_COUNTRY_HINTS.get(normalized, "")


def _guess_google_play_locale(geo: str | None) -> tuple[str, str]:
    country = _guess_country_code(geo)
    if not country:
        return "", ""
    return _GOOGLE_PLAY_LOCALE_HINTS.get(country, (country.upper(), country.lower()))


DEFAULT_LOOKBACK_DAYS = 730


class ReputationIngestService:
    """Ingesta de reputación: carga config, ejecuta collectors y guarda cache."""

    def __init__(self) -> None:
        self._settings = settings
        self._repo = ReputationCacheRepo(self._settings.cache_path)

    def run(
        self,
        force: bool = False,
        progress: ProgressCallback | None = None,
        sources_override: Sequence[str] | None = None,
    ) -> ReputationCacheDocument:
        def report(stage: str, pct: int, meta: dict[str, Any] | None = None) -> None:
            if not progress:
                return
            safe_pct = max(0, min(100, int(pct)))
            progress(stage, safe_pct, meta or {})

        # Relee .env.reputation para que los toggles activos se apliquen siempre.
        reload_reputation_settings()
        # Refresca el repo por si cambió la ruta del cache/perfil.
        self._repo = ReputationCacheRepo(self._settings.cache_path)

        cfg = _as_dict(load_business_config())
        cfg_hash = compute_config_hash(cfg)
        ttl_hours = effective_ttl_hours(cfg)
        if sources_override is None:
            raw_sources = list(self._settings.enabled_sources())
        else:
            raw_sources = [source for source in sources_override if source]
        sources_enabled: list[str] = []
        for source in raw_sources:
            normalized = source.strip().lower()
            if normalized and normalized not in sources_enabled:
                sources_enabled.append(normalized)
        enabled_sources = set(sources_enabled)
        lookback_days = DEFAULT_LOOKBACK_DAYS
        report(
            "Preparando configuración",
            4,
            {"sources_enabled": len(sources_enabled), "lookback_days": lookback_days},
        )
        logger.info("Reputation ingest started (force=%s)", force)
        logger.debug("Sources enabled: %s", sources_enabled)

        existing = self._repo.load()

        def is_doc_fresh(doc: ReputationCacheDocument | None) -> bool:
            if not doc:
                return False
            now = datetime.now(timezone.utc)
            age_hours = (now - doc.generated_at).total_seconds() / 3600.0
            return age_hours <= ttl_hours

        collectors, notes = self._build_collectors(cfg, sources_enabled)
        if enabled_sources and collectors:
            before = len(collectors)
            collectors = [
                collector
                for collector in collectors
                if getattr(collector, "source_name", "").strip().lower() in enabled_sources
            ]
            dropped = before - len(collectors)
            if dropped:
                notes.append(f"sources filtered: dropped {dropped} collectors not enabled")
        report("Colectores listos", 12, {"collectors": len(collectors)})

        def filter_enabled(items: list[ReputationItem]) -> list[ReputationItem]:
            if not enabled_sources:
                return []
            return [
                item for item in items if (item.source or "").strip().lower() in enabled_sources
            ]

        # Reutiliza cache si aplica y no hay collectors activos
        if (
            not force
            and existing
            and existing.config_hash == cfg_hash
            and is_doc_fresh(existing)
            and not collectors
        ):
            cache_note = "; ".join(notes) if notes else "cache hit"
            logger.info("Reputation cache hit (%s items)", len(existing.items))
            filtered_items = self._drop_invalid_items(
                filter_enabled(existing.items),
                notes,
            )
            filtered_ratings = [
                entry
                for entry in existing.market_ratings
                if entry.source.strip().lower() in enabled_sources
            ]
            filtered_history = [
                entry
                for entry in existing.market_ratings_history
                if entry.source.strip().lower() in enabled_sources
            ]
            if len(filtered_items) != len(existing.items):
                cache_note = f"{cache_note}; sources filtered"
            report(
                "Cache vigente",
                100,
                {"items": len(filtered_items), "note": cache_note},
            )
            return ReputationCacheDocument(
                generated_at=datetime.now(timezone.utc),
                config_hash=cfg_hash,
                sources_enabled=sources_enabled,
                items=filtered_items,
                market_ratings=filtered_ratings,
                market_ratings_history=filtered_history,
                stats=ReputationCacheStats(count=len(filtered_items), note=cache_note),
            )

        report("Recolectando señales", 20, {"collectors": len(collectors)})

        def on_collector(done: int, total: int, source_name: str) -> None:
            if total <= 0:
                report("Recolectando señales", 35, {"collectors": 0})
                return
            pct = 20 + int((45 - 20) * (done / total))
            report(
                f"Recolectando {source_name}",
                pct,
                {"collector": source_name, "done": done, "total": total},
            )

        items = self._collect_items(collectors, notes, progress=on_collector)
        items = self._drop_invalid_items(items, notes)
        if items:
            items = self._merge_items([], items)
        report("Señales recolectadas", 45, {"items": len(items)})
        items = filter_enabled(items)

        items = self._normalize_items(items, lookback_days)
        report("Normalizando señales", 52, {"items": len(items)})
        items = self._apply_geo_hints(cfg, items)
        report("Aplicando geografía", 58)
        if "appstore" in enabled_sources and any(item.source == "appstore" for item in items):
            items = self._apply_appstore_actor_map(cfg, items)
            report("Mapeando App Store", 62)
        else:
            report("Mapeo App Store omitido", 62)

        if "google_play" in enabled_sources and any(item.source == "google_play" for item in items):
            items = self._apply_google_play_actor_map(cfg, items)
            report("Mapeando Google Play", 66)
        else:
            report("Mapeo Google Play omitido", 66)
        items = self._apply_sentiment(cfg, items, existing.items if existing else None, notes)
        report("Analizando sentimiento", 74)
        items = self._filter_noise_items(cfg, items, notes)
        report("Filtrando ruido", 82)
        items = self._balance_items(
            cfg,
            items,
            existing.items if existing else [],
            lookback_days,
            notes,
            sources_enabled,
        )
        report("Balanceando señales", 90)
        existing_items = (
            self._drop_invalid_items(filter_enabled(existing.items), notes) if existing else []
        )
        merged_items = self._merge_items(existing_items, items)
        merged_items = filter_enabled(merged_items)
        report("Fusionando items", 94)
        merged_items = self._filter_noise_items(cfg, merged_items, notes)
        report("Último ajuste", 96)
        market_ratings = self._collect_market_ratings(cfg, notes, sources_enabled)
        market_ratings_history = self._merge_market_ratings_history(
            [
                entry
                for entry in (existing.market_ratings_history if existing else [])
                if entry.source.strip().lower() in enabled_sources
            ],
            market_ratings,
        )
        final_note: str | None = "; ".join(notes) if notes else None

        doc = ReputationCacheDocument(
            generated_at=datetime.now(timezone.utc),
            config_hash=cfg_hash,
            sources_enabled=sources_enabled,
            items=merged_items,
            market_ratings=market_ratings,
            market_ratings_history=market_ratings_history,
            stats=ReputationCacheStats(count=len(merged_items), note=final_note),
        )

        self._repo.save(doc)
        logger.info("Reputation ingest finished (%s items)", len(merged_items))
        report("Cache actualizada", 100, {"items": len(merged_items), "note": final_note})

        return doc

    @staticmethod
    def _collect_items(
        collectors: Iterable[ReputationCollector],
        notes: list[str],
        progress: CollectorProgress | None = None,
    ) -> list[ReputationItem]:
        items: list[ReputationItem] = []
        collector_list = list(collectors)
        if not collector_list:
            return items
        total = len(collector_list)
        done = 0
        diag = _env_bool(os.getenv("REPUTATION_COLLECTOR_DIAG", "false"))
        raw_slow = os.getenv("REPUTATION_COLLECTOR_SLOW_SEC", "8").strip()
        try:
            slow_threshold = float(raw_slow) if raw_slow else 8.0
        except ValueError:
            slow_threshold = 8.0
        if slow_threshold < 0:
            slow_threshold = 0.0

        def maybe_note(collector: ReputationCollector, duration: float, count: int) -> None:
            if diag or (slow_threshold and duration >= slow_threshold):
                notes.append(f"collector: {collector.source_name} {duration:.1f}s items={count}")

        workers = _env_int("REPUTATION_COLLECTOR_WORKERS", 6)
        if workers <= 1 or len(collector_list) == 1:
            for collector in collector_list:
                try:
                    started = time.perf_counter()
                    batch = list(collector.collect())
                    duration = time.perf_counter() - started
                    items.extend(batch)
                    maybe_note(collector, duration, len(batch))
                except Exception as exc:  # pragma: no cover - defensive
                    notes.append(f"{collector.source_name}: error {exc}")
                    logger.warning("Collector %s failed: %s", collector.source_name, exc)
                finally:
                    done += 1
                    if progress:
                        progress(done, total, collector.source_name)
            return items

        max_workers = max(1, min(workers, len(collector_list)))

        def _run(
            collector: ReputationCollector,
        ) -> tuple[list[ReputationItem], float]:
            started = time.perf_counter()
            batch = list(collector.collect())
            duration = time.perf_counter() - started
            return batch, duration

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_run, collector): collector for collector in collector_list
            }
            for future in as_completed(future_map):
                collector = future_map[future]
                try:
                    batch, duration = future.result()
                    items.extend(batch)
                    maybe_note(collector, duration, len(batch))
                except Exception as exc:  # pragma: no cover - defensive
                    notes.append(f"{collector.source_name}: error {exc}")
                    logger.warning("Collector %s failed: %s", collector.source_name, exc)
                finally:
                    done += 1
                    if progress:
                        progress(done, total, collector.source_name)
        return items

    @staticmethod
    def _drop_invalid_items(
        items: list[ReputationItem],
        notes: list[str],
    ) -> list[ReputationItem]:
        if not items:
            return items
        filtered: list[ReputationItem] = []
        dropped = 0
        for item in items:
            if not item.id or not item.source:
                dropped += 1
                continue
            filtered.append(item)
        if dropped:
            notes.append(f"sanity: dropped {dropped} items missing id/source")
        return filtered

    @classmethod
    def _apply_appstore_actor_map(
        cls, cfg: dict[str, Any], items: list[ReputationItem]
    ) -> list[ReputationItem]:
        app_cfg = _as_dict(cfg.get("appstore"))
        mapping: dict[str, str] = {}
        if isinstance(app_cfg, dict):
            raw_map = app_cfg.get("app_id_to_actor")
            if isinstance(raw_map, dict):
                for key, value in raw_map.items():
                    if (
                        isinstance(key, str)
                        and isinstance(value, str)
                        and key.strip()
                        and value.strip()
                    ):
                        mapping[key.strip()] = value.strip()
            # Optional: allow per-geo actor mappings in app_ids_by_geo_actor
            raw_by_geo = app_cfg.get("app_ids_by_geo_actor")
            if isinstance(raw_by_geo, dict):
                for _, geo_entries in raw_by_geo.items():
                    if isinstance(geo_entries, dict):
                        for key, value in geo_entries.items():
                            if (
                                isinstance(key, str)
                                and isinstance(value, str)
                                and key.strip()
                                and value.strip()
                            ):
                                mapping.setdefault(key.strip(), value.strip())
                    elif isinstance(geo_entries, list):
                        for entry in geo_entries:
                            if not isinstance(entry, dict):
                                continue
                            app_id = entry.get("id")
                            actor = entry.get("actor")
                            if (
                                isinstance(app_id, str)
                                and isinstance(actor, str)
                                and app_id.strip()
                                and actor.strip()
                            ):
                                mapping.setdefault(app_id.strip(), actor.strip())
        if not mapping:
            return items

        alias_map = build_actor_alias_map(cfg)
        for item in items:
            if item.source != "appstore":
                continue
            if item.actor and item.actor.strip():
                continue
            app_id = (item.signals or {}).get("app_id")
            if not app_id:
                continue
            actor_raw = mapping.get(str(app_id))
            if not isinstance(actor_raw, str) or not actor_raw.strip():
                continue
            actor = canonicalize_actor(actor_raw, alias_map) if alias_map else actor_raw.strip()
            if not actor:
                continue
            item.actor = actor
            if item.signals is not None:
                actors = item.signals.get("actors")
                if isinstance(actors, list):
                    if actor not in actors:
                        item.signals["actors"] = [actor] + [a for a in actors if a != actor]
                else:
                    item.signals["actors"] = [actor]
                item.signals["actor_source"] = "app_id"
        return items

    @staticmethod
    def _normalize_items(items: list[ReputationItem], lookback_days: int) -> list[ReputationItem]:
        now = datetime.now(timezone.utc)
        min_dt = now - timedelta(days=max(0, lookback_days))
        filtered: list[ReputationItem] = []

        for item in items:
            if item.collected_at is None:
                item.collected_at = now
            compare_dt = item.published_at or item.collected_at
            if compare_dt and compare_dt >= min_dt:
                filtered.append(item)

        return filtered

    def _collect_market_ratings(
        self,
        cfg: dict[str, Any],
        notes: list[str],
        sources_enabled: Sequence[str],
    ) -> list[MarketRating]:
        enabled = {source.lower() for source in sources_enabled}
        ratings: list[MarketRating] = []
        if "appstore" in enabled:
            ratings.extend(self._collect_appstore_market_ratings(cfg, notes))
        if "google_play" in enabled:
            ratings.extend(self._collect_google_play_market_ratings(cfg, notes))
        return ratings

    @staticmethod
    def _merge_market_ratings_history(
        history: Sequence[MarketRating],
        latest: Sequence[MarketRating],
    ) -> list[MarketRating]:
        merged = list(history)
        last_by_key: dict[tuple[str, str, str, str, str], MarketRating] = {}

        for entry in history:
            key = _market_rating_key(entry)
            current = last_by_key.get(key)
            if current is None or _market_rating_is_newer(entry, current):
                last_by_key[key] = entry

        for entry in latest:
            key = _market_rating_key(entry)
            last = last_by_key.get(key)
            if last and _market_rating_is_same(last, entry):
                continue
            merged.append(entry)
            last_by_key[key] = entry

        return merged

    def _collect_appstore_market_ratings(
        self,
        cfg: dict[str, Any],
        notes: list[str],
    ) -> list[MarketRating]:
        appstore_cfg = _as_dict(cfg.get("appstore"))
        app_ids_by_geo = appstore_cfg.get("app_ids_by_geo") or {}
        app_ids = appstore_cfg.get("app_ids") or []
        if not app_ids_by_geo and app_ids:
            app_ids_by_geo = {"Global": app_ids}
        if not isinstance(app_ids_by_geo, dict):
            return []

        country_by_geo = appstore_cfg.get("country_by_geo") or {}
        if not isinstance(country_by_geo, dict):
            country_by_geo = {}
        app_id_to_actor = appstore_cfg.get("app_id_to_actor") or {}
        if not isinstance(app_id_to_actor, dict):
            app_id_to_actor = {}

        fallback_actor = _primary_actor_canonical(cfg)
        default_country = os.getenv("APPSTORE_COUNTRY", "es").strip().lower() or "es"
        timeout = _env_int("APPSTORE_RATING_TIMEOUT", 12)
        seen: set[tuple[str, str]] = set()
        out: list[MarketRating] = []
        now = datetime.now(timezone.utc)

        for geo, app_ids_list in app_ids_by_geo.items():
            if not isinstance(app_ids_list, list):
                continue
            country = str(country_by_geo.get(geo, "")).strip().lower()
            if not country:
                country = _guess_country_code(geo) or default_country
            if not country:
                notes.append(f"appstore rating: missing country for geo '{geo}'")
                continue
            for app_id in app_ids_list:
                if not isinstance(app_id, str) or not app_id.strip():
                    continue
                key = (app_id, country)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    rating_info = _fetch_appstore_rating(app_id, country, timeout)
                except Exception as exc:  # pragma: no cover - defensive
                    notes.append(f"appstore rating: error {app_id} {country}: {exc}")
                    continue
                if rating_info is None:
                    continue
                rating, rating_count, url, name = rating_info
                if rating is None:
                    continue
                actor = app_id_to_actor.get(app_id) or fallback_actor
                out.append(
                    MarketRating(
                        source="appstore",
                        actor=str(actor) if actor else None,
                        geo=str(geo) if geo else None,
                        app_id=app_id,
                        rating=float(rating),
                        rating_count=rating_count,
                        url=url,
                        name=name,
                        collected_at=now,
                    )
                )

        return out

    def _collect_google_play_market_ratings(
        self,
        cfg: dict[str, Any],
        notes: list[str],
    ) -> list[MarketRating]:
        play_cfg = _as_dict(cfg.get("google_play"))
        package_ids_by_geo = play_cfg.get("package_ids_by_geo") or {}
        package_ids = play_cfg.get("package_ids") or []
        if not package_ids_by_geo and package_ids:
            package_ids_by_geo = {"Global": package_ids}
        if not isinstance(package_ids_by_geo, dict):
            return []

        geo_to_gl = play_cfg.get("geo_to_gl") or {}
        if not isinstance(geo_to_gl, dict):
            geo_to_gl = {}
        geo_to_hl = play_cfg.get("geo_to_hl") or {}
        if not isinstance(geo_to_hl, dict):
            geo_to_hl = {}
        package_id_to_actor = play_cfg.get("package_id_to_actor") or {}
        if not isinstance(package_id_to_actor, dict):
            package_id_to_actor = {}

        fallback_actor = _primary_actor_canonical(cfg)
        timeout = _env_int("GOOGLE_PLAY_RATING_TIMEOUT", 12)
        default_gl = os.getenv("GOOGLE_PLAY_DEFAULT_COUNTRY", "ES").strip().upper() or "ES"
        default_hl = os.getenv("GOOGLE_PLAY_DEFAULT_LANGUAGE", "es").strip().lower() or "es"
        seen: set[tuple[str, str, str]] = set()
        out: list[MarketRating] = []
        now = datetime.now(timezone.utc)

        for geo, packages in package_ids_by_geo.items():
            if not isinstance(packages, list):
                continue
            gl = str(geo_to_gl.get(geo, "")).strip().upper()
            hl = str(geo_to_hl.get(geo, "")).strip().lower()
            if not gl or not hl:
                guessed_gl, guessed_hl = _guess_google_play_locale(geo)
                gl = gl or guessed_gl or default_gl
                hl = hl or guessed_hl or default_hl
            if not gl or not hl:
                notes.append(f"google_play rating: missing hl/gl for geo '{geo}'")
                continue
            for package_id in packages:
                if not isinstance(package_id, str) or not package_id.strip():
                    continue
                key = (package_id, gl, hl)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    rating_info = _fetch_google_play_rating(package_id, gl, hl, timeout)
                except Exception as exc:  # pragma: no cover - defensive
                    notes.append(f"google_play rating: error {package_id} {gl}/{hl}: {exc}")
                    continue
                if rating_info is None:
                    continue
                rating, rating_count, url, name = rating_info
                if rating is None:
                    continue
                actor = package_id_to_actor.get(package_id) or fallback_actor
                out.append(
                    MarketRating(
                        source="google_play",
                        actor=str(actor) if actor else None,
                        geo=str(geo) if geo else None,
                        package_id=package_id,
                        rating=float(rating),
                        rating_count=rating_count,
                        url=url,
                        name=name,
                        collected_at=now,
                    )
                )
        return out

    @classmethod
    def _apply_google_play_actor_map(
        cls, cfg: dict[str, Any], items: list[ReputationItem]
    ) -> list[ReputationItem]:
        gp_cfg = _as_dict(cfg.get("google_play"))
        mapping = gp_cfg.get("package_id_to_actor") if isinstance(gp_cfg, dict) else None
        if not isinstance(mapping, dict) or not mapping:
            return items

        alias_map = build_actor_alias_map(cfg)
        for item in items:
            if item.source != "google_play":
                continue
            if item.actor and item.actor.strip():
                continue
            package_id = (item.signals or {}).get("package_id")
            if not package_id:
                continue
            actor_raw = mapping.get(str(package_id))
            if not isinstance(actor_raw, str) or not actor_raw.strip():
                continue
            actor = canonicalize_actor(actor_raw, alias_map) if alias_map else actor_raw.strip()
            if not actor:
                continue
            item.actor = actor
            if item.signals is not None:
                actors = item.signals.get("actors")
                if isinstance(actors, list):
                    if actor not in actors:
                        item.signals["actors"] = [actor] + [a for a in actors if a != actor]
                else:
                    item.signals["actors"] = [actor]
                item.signals["actor_source"] = "package_id"
        return items

    @classmethod
    def _apply_geo_hints(
        cls, cfg: dict[str, Any], items: list[ReputationItem]
    ) -> list[ReputationItem]:
        geos = [g.strip() for g in cfg.get("geografias", []) if isinstance(g, str) and g.strip()]
        geo_aliases_raw = cfg.get("geografias_aliases") or {}
        geo_aliases: dict[str, list[str]] = {}
        if isinstance(geo_aliases_raw, dict):
            for geo, aliases in geo_aliases_raw.items():
                if not isinstance(geo, str):
                    continue
                if not isinstance(aliases, list):
                    continue
                cleaned = [a.strip() for a in aliases if isinstance(a, str) and a.strip()]
                if cleaned:
                    geo_aliases[geo] = cleaned
        source_geo_map = cls._build_source_geo_map(cfg, geos)
        if not geos and not source_geo_map:
            return items

        actor_geo_map = cls._build_actor_geo_map(cfg)

        for item in items:
            if not item.geo:
                actor_geo = cls._infer_geo_from_actor(item, actor_geo_map)
                if actor_geo:
                    item.geo = actor_geo
                    item.signals["geo_source"] = "actor"
                    continue

            title_only = item.title or ""
            content_geo = cls._detect_geo_in_text(title_only, geos, geo_aliases)
            if not content_geo:
                text = f"{item.title or ''} {item.text or ''}"
                content_geo = cls._detect_geo_in_text(text, geos, geo_aliases)
            if content_geo:
                if item.geo != content_geo:
                    item.geo = content_geo
                    item.signals["geo_source"] = "content"
                continue

            source_geo = cls._infer_geo_from_source(item, source_geo_map)
            if source_geo and item.geo != source_geo:
                item.geo = source_geo
                item.signals["geo_source"] = "source"

        return items

    @staticmethod
    def _build_actor_geo_map(cfg: dict[str, Any]) -> dict[str, list[str]]:
        actor_geo_map: dict[str, list[str]] = {}
        raw = cfg.get("otros_actores_por_geografia") or {}
        if not isinstance(raw, dict):
            return actor_geo_map

        alias_map = build_actor_alias_map(cfg)
        for geo, actors in raw.items():
            if not isinstance(geo, str) or not geo.strip():
                continue
            if not isinstance(actors, list):
                continue
            for actor in actors:
                if not isinstance(actor, str) or not actor.strip():
                    continue
                canonical = canonicalize_actor(actor, alias_map) if alias_map else actor.strip()
                if not canonical:
                    continue
                bucket = actor_geo_map.setdefault(canonical, [])
                if geo not in bucket:
                    bucket.append(geo)
        return actor_geo_map

    @staticmethod
    def _infer_geo_from_actor(
        item: ReputationItem, actor_geo_map: dict[str, list[str]]
    ) -> str | None:
        actor = item.actor or ""
        if not actor:
            signals = item.signals or {}
            actors_signal = signals.get("actors")
            if isinstance(actors_signal, list):
                for value in actors_signal:
                    if isinstance(value, str) and value.strip():
                        actor = value
                        break
        if not actor:
            return None
        geos = actor_geo_map.get(actor)
        if not geos or len(geos) != 1:
            return None
        return geos[0]

    @staticmethod
    def _merge_items(
        existing: list[ReputationItem], incoming: list[ReputationItem]
    ) -> list[ReputationItem]:
        merged: dict[tuple[str, str], ReputationItem] = {
            (item.source, item.id): item for item in existing
        }
        for item in incoming:
            key = (item.source, item.id)
            if key not in merged:
                merged[key] = item
                continue
            current = merged[key]
            if not current.actor and item.actor:
                current.actor = item.actor
            if item.geo and (
                not current.geo
                or (
                    current.geo != item.geo
                    and item.signals
                    and item.signals.get("geo_source") in {"source", "content"}
                )
            ):
                current.geo = item.geo
            if not current.language and item.language:
                current.language = item.language
            if not current.title and item.title:
                current.title = item.title
            if item.text and (not current.text or len(item.text) > len(current.text)):
                current.text = item.text
            if not current.sentiment and item.sentiment:
                current.sentiment = item.sentiment
            if item.signals:
                merged_signals = dict(current.signals)
                merged_signals.update(item.signals)
                actors = set()
                for value in (current.signals.get("actors"), item.signals.get("actors")):
                    if isinstance(value, list):
                        actors.update([str(v) for v in value if v])
                if actors:
                    merged_signals["actors"] = list(sorted(actors))
                current.signals = merged_signals
        return list(merged.values())

    def _apply_sentiment(
        self,
        cfg: dict[str, Any],
        items: list[ReputationItem],
        existing: list[ReputationItem] | None = None,
        notes: list[str] | None = None,
    ) -> list[ReputationItem]:
        keywords = self._load_keywords(cfg)
        cfg_local = dict(cfg)
        cfg_local["keywords"] = keywords
        service = ReputationSentimentService(cfg_local)
        target_language = _resolve_translation_language()
        existing_keys = {(item.source, item.id) for item in existing} if existing else set()
        if existing_keys:
            new_items = [item for item in items if (item.source, item.id) not in existing_keys]
            if target_language:
                new_items = service.translate_items(new_items, target_language)
            updated = service.analyze_items(new_items)
            updated_map = {(item.source, item.id): item for item in updated}
            result = [updated_map.get((item.source, item.id), item) for item in items]
        else:
            if target_language:
                items = service.translate_items(items, target_language)
            result = service.analyze_items(items)

        if service.llm_warning and notes is not None:
            notes.append(service.llm_warning)
        return result

    @classmethod
    def _filter_noise_items(
        cls,
        cfg: dict[str, Any],
        items: list[ReputationItem],
        notes: list[str],
    ) -> list[ReputationItem]:
        require_actor_sources = cls._load_sources_list(cfg.get("require_actor_sources"))
        require_context_sources = cls._load_sources_list(cfg.get("require_context_sources"))
        noise_sources = cls._load_sources_list(cfg.get("noise_filter_sources"))
        if not require_actor_sources:
            require_actor_sources = _ACTOR_REQUIRED_SOURCES
        if not noise_sources:
            noise_sources = require_actor_sources

        noise_terms = cls._load_noise_terms(cfg)
        context_terms = cls._build_context_terms(cfg)
        alias_map = build_actor_alias_map(cfg)
        aliases_by_canonical = build_actor_aliases_by_canonical(cfg)
        guard_actors = cls._load_guard_actors(cfg, alias_map)
        allowed_by_geo, known_actors = cls._build_actor_geo_allowlist(cfg, alias_map)
        source_context_terms: dict[str, list[str]] = {}
        if require_context_sources:
            for source in require_context_sources:
                extra_terms: list[str] = []
                raw_source_cfg = cfg.get(source) or {}
                if isinstance(raw_source_cfg, dict):
                    raw_terms = raw_source_cfg.get("query_terms") or []
                    if isinstance(raw_terms, list):
                        extra_terms = [
                            t.strip() for t in raw_terms if isinstance(t, str) and t.strip()
                        ]
                combined = list(dict.fromkeys([*context_terms, *extra_terms]))
                source_context_terms[source] = combined
        filtered: list[ReputationItem] = []
        dropped_actor = 0
        dropped_actor_text = 0
        dropped_guard = 0
        dropped_geo = 0
        dropped_noise = 0
        dropped_context = 0

        for item in items:
            text = f"{item.title or ''} {item.text or ''}".strip()
            if item.source in require_actor_sources and not cls._item_has_actor(item):
                dropped_actor += 1
                continue
            if item.source in require_actor_sources and not cls._item_actor_in_text(
                item, alias_map, aliases_by_canonical
            ):
                dropped_actor_text += 1
                continue
            if require_context_sources and item.source in require_context_sources:
                terms = source_context_terms.get(item.source, context_terms)
                if text and terms and not match_keywords(text, terms):
                    dropped_context += 1
                    continue
            if (
                allowed_by_geo
                and item.geo
                and not cls._item_actor_allowed_for_geo(
                    item, item.geo, allowed_by_geo, known_actors, alias_map
                )
            ):
                dropped_geo += 1
                continue
            if (
                guard_actors
                and cls._item_has_guard_actor(item, guard_actors, alias_map)
                and text
                and context_terms
                and not match_keywords(text, context_terms)
            ):
                dropped_guard += 1
                continue
            if (
                noise_terms
                and item.source in noise_sources
                and text
                and match_keywords(text, noise_terms)
                and (not context_terms or not match_keywords(text, context_terms))
            ):
                dropped_noise += 1
                continue
            filtered.append(item)

        if (
            dropped_actor
            or dropped_actor_text
            or dropped_guard
            or dropped_geo
            or dropped_noise
            or dropped_context
        ):
            total_dropped = (
                dropped_actor
                + dropped_actor_text
                + dropped_guard
                + dropped_geo
                + dropped_noise
                + dropped_context
            )
            notes.append(
                "filter: dropped %s items (missing_actor=%s, actor_text=%s, context=%s, guard=%s, geo=%s, noise=%s)"
                % (
                    total_dropped,
                    dropped_actor,
                    dropped_actor_text,
                    dropped_context,
                    dropped_guard,
                    dropped_geo,
                    dropped_noise,
                )
            )
        return filtered

    @staticmethod
    def _item_has_actor(item: ReputationItem) -> bool:
        if item.actor and item.actor.strip():
            return True
        signals = item.signals or {}
        actors = signals.get("actors")
        if isinstance(actors, list):
            return any(isinstance(actor, str) and actor.strip() for actor in actors)
        return False

    @staticmethod
    def _item_actor_candidates(item: ReputationItem) -> list[str]:
        candidates: list[str] = []
        if item.actor and item.actor.strip():
            candidates.append(item.actor.strip())
        signals = item.signals or {}
        actors = signals.get("actors")
        if isinstance(actors, list):
            for actor in actors:
                if isinstance(actor, str) and actor.strip():
                    candidates.append(actor.strip())
        return list(dict.fromkeys(candidates))

    @classmethod
    def _item_actor_in_text(
        cls,
        item: ReputationItem,
        alias_map: dict[str, str],
        aliases_by_canonical: dict[str, list[str]],
    ) -> bool:
        text = f"{item.title or ''} {item.text or ''}".strip()
        if not text:
            return False
        candidates = cls._item_actor_candidates(item)
        if not candidates:
            return False
        for candidate in candidates:
            if match_keywords(text, [candidate]):
                return True
            canonical = canonicalize_actor(candidate, alias_map) if alias_map else candidate
            if canonical and canonical != candidate and match_keywords(text, [canonical]):
                return True
            aliases = aliases_by_canonical.get(canonical) or []
            for alias in aliases:
                if match_keywords(text, [alias]):
                    return True
        return False

    @staticmethod
    def _load_guard_actors(cfg: dict[str, Any], alias_map: dict[str, str]) -> set[str]:
        raw = cfg.get("actor_context_guard") or []
        if not isinstance(raw, list):
            return set()
        guard: set[str] = set()
        for value in raw:
            if isinstance(value, str) and value.strip():
                canonical = canonicalize_actor(value, alias_map) if alias_map else value.strip()
                if canonical:
                    guard.add(canonical)
        return guard

    @classmethod
    def _item_has_guard_actor(
        cls,
        item: ReputationItem,
        guard_actors: set[str],
        alias_map: dict[str, str],
    ) -> bool:
        if not guard_actors:
            return False
        for candidate in cls._item_actor_candidates(item):
            canonical = canonicalize_actor(candidate, alias_map) if alias_map else candidate
            if canonical in guard_actors:
                return True
        return False

    @staticmethod
    def _normalize_geo_key(value: str) -> str:
        return normalize_text(value or "")

    @classmethod
    def _build_actor_geo_allowlist(
        cls,
        cfg: dict[str, Any],
        alias_map: dict[str, str],
    ) -> tuple[dict[str, set[str]], set[str]]:
        allowed_by_geo: dict[str, set[str]] = {}
        known_actors: set[str] = set()

        def _canonical(name: str) -> str:
            if not name:
                return ""
            if alias_map:
                return canonicalize_actor(name, alias_map)
            return name.strip()

        principal = actor_principal_canonicals(cfg)
        global_actors = cfg.get("otros_actores_globales") or []
        base: set[str] = set()
        for name in [*principal, *global_actors]:
            if isinstance(name, str) and name.strip():
                canonical = _canonical(name.strip())
                if canonical:
                    base.add(canonical)
                    known_actors.add(canonical)

        raw_by_geo = cfg.get("otros_actores_por_geografia") or {}
        if isinstance(raw_by_geo, dict):
            for geo, names in raw_by_geo.items():
                if not isinstance(geo, str) or not geo.strip():
                    continue
                bucket = set(base)
                if isinstance(names, list):
                    for name in names:
                        if not isinstance(name, str) or not name.strip():
                            continue
                        canonical = _canonical(name.strip())
                        if canonical:
                            bucket.add(canonical)
                            known_actors.add(canonical)
                allowed_by_geo[cls._normalize_geo_key(geo)] = bucket

        geos = cfg.get("geografias") or []
        if isinstance(geos, list):
            for geo in geos:
                if isinstance(geo, str) and geo.strip():
                    key = cls._normalize_geo_key(geo)
                    allowed_by_geo.setdefault(key, set(base))

        if alias_map:
            known_actors.update(alias_map.values())

        return allowed_by_geo, known_actors

    @classmethod
    def _item_actor_allowed_for_geo(
        cls,
        item: ReputationItem,
        geo: str,
        allowed_by_geo: dict[str, set[str]],
        known_actors: set[str],
        alias_map: dict[str, str],
    ) -> bool:
        geo_key = cls._normalize_geo_key(geo)
        allowed = allowed_by_geo.get(geo_key)
        if not allowed:
            return True
        candidates = cls._item_actor_candidates(item)
        if not candidates:
            return True
        matched_known = False
        for candidate in candidates:
            canonical = canonicalize_actor(candidate, alias_map) if alias_map else candidate
            if canonical in known_actors:
                matched_known = True
                if canonical in allowed:
                    return True
        return not matched_known

    @staticmethod
    def _load_sources_list(value: object) -> set[str]:
        if not isinstance(value, list):
            return set()
        sources = {
            str(item).strip().lower() for item in value if isinstance(item, str) and item.strip()
        }
        return {source for source in sources if source}

    @staticmethod
    def _load_noise_terms(cfg: dict[str, Any]) -> list[str]:
        raw = cfg.get("noise_terms") or []
        if not isinstance(raw, list):
            return []
        return [term.strip() for term in raw if isinstance(term, str) and term.strip()]

    @staticmethod
    def _build_context_terms(cfg: dict[str, Any]) -> list[str]:
        segment_terms = [
            t.strip() for t in cfg.get("segment_terms", []) if isinstance(t, str) and t.strip()
        ]
        override_terms = [
            t.strip() for t in cfg.get("context_terms", []) if isinstance(t, str) and t.strip()
        ]
        if override_terms:
            return list(dict.fromkeys([*segment_terms, *override_terms]))

        strict = bool(cfg.get("context_terms_strict"))
        base_terms_strict = [
            "banco",
            "bank",
            "banca",
            "finanzas",
            "financiero",
            "financiera",
            "cuenta",
            "tarjeta",
            "transferencia",
            "credito",
            "crédito",
            "debito",
            "débito",
            "app",
        ]
        base_terms_relaxed = [
            *base_terms_strict,
            "empresa",
            "empresas",
            "pyme",
            "pymes",
        ]
        base_terms = base_terms_strict if strict else base_terms_relaxed
        return list(dict.fromkeys([*segment_terms, *base_terms]))

    @staticmethod
    def _normalize_actor(name: str, alias_map: dict[str, str]) -> str:
        if not name:
            return ""
        if not alias_map:
            return name.strip()
        return canonicalize_actor(name, alias_map)

    @classmethod
    def _all_actors(cls, cfg: dict[str, Any], alias_map: dict[str, str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []

        def add(name: str) -> None:
            normalized = cls._normalize_actor(name, alias_map)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            ordered.append(normalized)

        actors_by_geo = cfg.get("otros_actores_por_geografia") or {}
        if isinstance(actors_by_geo, dict):
            for _, names in actors_by_geo.items():
                if isinstance(names, list):
                    for name in names:
                        if isinstance(name, str) and name.strip():
                            add(name)
        for name in cfg.get("otros_actores_globales") or []:
            if isinstance(name, str) and name.strip():
                add(name)
        for name in actor_principal_canonicals(cfg):
            add(name)
        return ordered

    def _count_distribution(
        self,
        items: list[ReputationItem],
        geos: list[str],
        actors: list[str],
        alias_map: dict[str, str],
    ) -> tuple[dict[str, int], dict[str, int]]:
        geo_counts = {geo: 0 for geo in geos}
        comp_counts = {comp: 0 for comp in actors}
        for item in items:
            if item.geo and item.geo in geo_counts:
                geo_counts[item.geo] += 1
            comps: set[str] = set()
            if item.actor:
                comps.add(self._normalize_actor(item.actor, alias_map))
            signals = item.signals or {}
            if isinstance(signals.get("actors"), list):
                for comp in signals["actors"]:
                    if isinstance(comp, str) and comp.strip():
                        comps.add(self._normalize_actor(comp, alias_map))
            for comp in comps:
                if comp in comp_counts:
                    comp_counts[comp] += 1
        return geo_counts, comp_counts

    @staticmethod
    def _load_balance_cfg() -> dict[str, Any]:
        enabled = _env_bool(os.getenv("REPUTATION_BALANCE_ENABLED", "true"))
        sources = _split_csv(os.getenv("REPUTATION_BALANCE_SOURCES", "news"))
        segment_terms = _split_csv(os.getenv("REPUTATION_BALANCE_SEGMENT_TERMS", ""))

        def _env_optional(env_name: str) -> str | None:
            value = os.getenv(env_name, "").strip()
            return value or None

        segment_query_mode = _env_optional("REPUTATION_BALANCE_SEGMENT_QUERY_MODE") or "broad"
        rss_query_geo_mode = _env_optional("REPUTATION_BALANCE_RSS_QUERY_GEO_MODE") or "required"
        rss_query_order = (
            _env_optional("REPUTATION_BALANCE_RSS_QUERY_ORDER") or "round_robin_geo_entity"
        )

        return {
            "enabled": enabled,
            "min_per_geo": _env_int("REPUTATION_BALANCE_MIN_PER_GEO", 40),
            "min_per_actor": _env_int("REPUTATION_BALANCE_MIN_PER_ACTOR", 25),
            "max_passes": _env_int("REPUTATION_BALANCE_MAX_PASSES", 3),
            "max_items_per_pass": _env_int("REPUTATION_BALANCE_MAX_ITEMS_PER_PASS", 400),
            "max_queries_per_pass": _env_int("REPUTATION_BALANCE_MAX_QUERIES_PER_PASS", 500),
            "max_geos": _env_int("REPUTATION_BALANCE_MAX_GEOS", 0),
            "max_actores": _env_int("REPUTATION_BALANCE_MAX_ACTORES", 0),
            "segment_query_mode": segment_query_mode,
            "segment_terms": segment_terms,
            "rss_query_geo_mode": rss_query_geo_mode,
            "rss_query_order": rss_query_order,
            "rss_query_max_total": _env_int("REPUTATION_BALANCE_RSS_QUERY_MAX_TOTAL", 600),
            "rss_query_max_per_geo": _env_int("REPUTATION_BALANCE_RSS_QUERY_MAX_PER_GEO", 120),
            "rss_query_max_per_entity": _env_int("REPUTATION_BALANCE_RSS_QUERY_MAX_PER_ENTITY", 20),
            "sources": sources or ["news"],
        }

    def _balance_items(
        self,
        cfg: dict[str, Any],
        items: list[ReputationItem],
        existing_items: list[ReputationItem],
        lookback_days: int,
        notes: list[str],
        sources_enabled: list[str],
    ) -> list[ReputationItem]:
        balance_cfg = self._load_balance_cfg()
        if not balance_cfg.get("enabled", False):
            return items

        sources_enabled_set = {s.strip().lower() for s in sources_enabled if s.strip()}
        balance_sources_raw = balance_cfg.get("sources") or ["news"]
        balance_sources = [
            str(source).strip().lower()
            for source in balance_sources_raw
            if isinstance(source, str) and source.strip()
        ]
        if not sources_enabled_set:
            notes.append("balance: skipped (no sources enabled)")
            return items
        active_balance_sources = [s for s in balance_sources if s in sources_enabled_set]
        if not active_balance_sources:
            notes.append("balance: skipped (balance sources not enabled)")
            return items

        min_per_geo = int(balance_cfg.get("min_per_geo", 0))
        min_per_actor = int(balance_cfg.get("min_per_actor", 0))
        max_passes = int(balance_cfg.get("max_passes", 0))
        if max_passes <= 0 or (min_per_geo <= 0 and min_per_actor <= 0):
            return items

        max_items_per_pass = int(balance_cfg.get("max_items_per_pass", 0))
        if max_items_per_pass <= 0:
            max_items_per_pass = _env_int("REPUTATION_DEFAULT_MAX_ITEMS", 1200)
        max_queries_per_pass = int(balance_cfg.get("max_queries_per_pass", 0))
        max_geos = int(balance_cfg.get("max_geos", 0))
        max_actores = int(balance_cfg.get("max_actores", 0))
        sources = active_balance_sources

        geos = [g for g in cfg.get("geografias", []) if isinstance(g, str) and g.strip()]
        alias_map = build_actor_alias_map(cfg)
        actors = self._all_actors(cfg, alias_map)

        existing_recent = (
            self._normalize_items(list(existing_items), lookback_days) if existing_items else []
        )
        combined = self._merge_items(existing_recent, items)

        for pass_idx in range(max_passes):
            geo_counts, comp_counts = self._count_distribution(combined, geos, actors, alias_map)
            missing_geos = [
                g for g in geos if min_per_geo > 0 and geo_counts.get(g, 0) < min_per_geo
            ]
            missing_actors = [
                c for c in actors if min_per_actor > 0 and comp_counts.get(c, 0) < min_per_actor
            ]
            if not missing_geos and not missing_actors:
                break
            if max_geos > 0:
                missing_geos = missing_geos[:max_geos]
            if max_actores > 0:
                missing_actors = missing_actors[:max_actores]

            new_items: list[ReputationItem] = []
            if "news" in sources:
                news_cfg = cfg.get("news") or {}
                focus_cfg = dict(cfg)
                focus_news = dict(news_cfg)
                for key in (
                    "rss_query_geo_mode",
                    "rss_query_order",
                    "rss_query_max_total",
                    "rss_query_max_per_geo",
                    "rss_query_max_per_entity",
                ):
                    override = balance_cfg.get(key)
                    if override:
                        focus_news[key] = override
                focus_cfg["news"] = focus_news

                segment_terms = self._load_segment_terms(cfg)
                segment_mode = self._segment_query_mode(cfg)
                balance_segment_terms = balance_cfg.get("segment_terms")
                if isinstance(balance_segment_terms, list) and balance_segment_terms:
                    segment_terms = [
                        t for t in balance_segment_terms if isinstance(t, str) and t.strip()
                    ]
                balance_segment_mode = balance_cfg.get("segment_query_mode")
                if isinstance(balance_segment_mode, str) and balance_segment_mode.strip():
                    segment_mode = balance_segment_mode.strip().lower()

                rss_geo_map = focus_news.get("rss_geo_map") or {}
                only_geos = set(missing_geos) if missing_geos else None
                only_entities = set(missing_actors) if missing_actors else None

                rss_sources: list[dict[str, str] | str] = []
                rss_urls = focus_news.get("rss_urls") or []
                if only_geos:
                    for entry in rss_urls:
                        if isinstance(entry, dict):
                            if entry.get("geo") in only_geos:
                                rss_sources.append(entry)
                        else:
                            rss_sources.append(entry)
                else:
                    rss_sources.extend(rss_urls)

                if _env_bool(os.getenv("NEWS_RSS_QUERY_ENABLED", "true")):
                    rss_sources.extend(
                        self._build_rss_queries(
                            "news",
                            focus_cfg,
                            rss_geo_map,
                            segment_terms,
                            segment_mode,
                            only_geos=only_geos,
                            only_entities=only_entities,
                        )
                    )
                if max_queries_per_pass > 0 and len(rss_sources) > max_queries_per_pass:
                    rss_sources = rss_sources[:max_queries_per_pass]

                if rss_sources:
                    api_key = os.getenv("NEWS_API_KEY", "").strip()
                    language = os.getenv("NEWS_LANG", "es").strip()
                    news_sources = os.getenv("NEWS_SOURCES", "").strip() or None
                    endpoint = os.getenv("NEWS_API_ENDPOINT", "").strip() or None

                    keywords = self._load_keywords(cfg)
                    entity_terms = self._load_entity_terms(cfg, keywords)

                    collector = NewsCollector(
                        api_key=api_key,
                        queries=[],
                        language=language,
                        max_articles=max_items_per_pass,
                        sources=news_sources,
                        endpoint=endpoint,
                        rss_urls=rss_sources,
                        rss_only=True,
                        filter_terms=entity_terms,
                    )
                    new_items.extend(list(collector.collect()))

            if not new_items:
                notes.append(
                    f"balance: pass {pass_idx + 1} no new items (missing geos={len(missing_geos)}, actors={len(missing_actors)})"
                )
                break

            new_items = self._normalize_items(new_items, lookback_days)
            new_items = self._apply_sentiment(cfg, new_items)
            items = self._merge_items(items, new_items)
            combined = self._merge_items(existing_recent, items)
            notes.append(
                f"balance: pass {pass_idx + 1} added {len(new_items)} items (missing geos={len(missing_geos)}, actors={len(missing_actors)})"
            )

        return items

    @staticmethod
    def _build_empty_doc(
        cfg_hash: str,
        sources_enabled: list[str],
        note: str | None = None,
    ) -> ReputationCacheDocument:
        return ReputationCacheDocument(
            generated_at=datetime.now(timezone.utc),
            config_hash=cfg_hash,
            sources_enabled=sources_enabled,
            items=[],
            market_ratings=[],
            market_ratings_history=[],
            stats=ReputationCacheStats(count=0, note=note),
        )

    def _build_collectors(
        self,
        cfg: dict[str, Any],
        sources_enabled: list[str],
    ) -> tuple[list[ReputationCollector], list[str]]:
        collectors: list[ReputationCollector] = []
        notes: list[str] = []
        handled_sources: set[str] = set()
        keywords = self._load_keywords(cfg)
        entity_terms = self._load_entity_terms(cfg, keywords)
        segment_terms = self._load_segment_terms(cfg)
        segment_mode = self._segment_query_mode(cfg)
        news_geo_map = (cfg.get("news") or {}).get("rss_geo_map") or {}

        if "appstore" in sources_enabled:
            handled_sources.add("appstore")
            appstore_cfg = _as_dict(cfg.get("appstore"))
            cfg_app_ids = _get_list_str(appstore_cfg, "app_ids")
            app_ids = list(cfg_app_ids)

            api_enabled = _env_bool(os.getenv("APPSTORE_API_ENABLED", "true"))
            country = os.getenv("APPSTORE_COUNTRY", "es").strip().lower() or "es"
            max_reviews = _env_int("APPSTORE_MAX_REVIEWS", 200)
            scrape_timeout = _env_int("APPSTORE_SCRAPE_TIMEOUT", 15)
            app_ids_by_geo = _get_dict_str_list_str(appstore_cfg, "app_ids_by_geo")
            country_by_geo = _get_dict_str_str(appstore_cfg, "country_by_geo")

            app_ids = list(dict.fromkeys(app_ids))
            if not app_ids and not app_ids_by_geo:
                notes.append("appstore: missing app_ids in config.json")
            else:
                for app_id_value in app_ids:
                    collectors.append(
                        self._build_appstore_collector(
                            api_enabled=api_enabled,
                            country=country,
                            app_id=app_id_value,
                            max_reviews=max_reviews,
                            scrape_timeout=scrape_timeout,
                            geo=None,
                        )
                    )
                for geo, geo_app_ids in app_ids_by_geo.items():
                    geo_country = country_by_geo.get(geo, country)
                    for app_id_value in geo_app_ids:
                        collectors.append(
                            self._build_appstore_collector(
                                api_enabled=api_enabled,
                                country=geo_country,
                                app_id=app_id_value,
                                max_reviews=max_reviews,
                                scrape_timeout=scrape_timeout,
                                geo=geo,
                            )
                        )

        if "google_play" in sources_enabled:
            handled_sources.add("google_play")
            gp_cfg = _as_dict(cfg.get("google_play"))
            cfg_packages = _get_list_str(gp_cfg, "package_ids")
            package_ids = list(cfg_packages)
            env_packages = os.getenv("GOOGLE_PLAY_PACKAGE_IDS", "").strip()
            if env_packages:
                package_ids.extend([p.strip() for p in env_packages.split(",") if p.strip()])

            api_enabled = _env_bool(os.getenv("GOOGLE_PLAY_API_ENABLED", "false"))
            gp_endpoint = os.getenv("GOOGLE_PLAY_API_ENDPOINT", "").strip()
            api_key = os.getenv("GOOGLE_PLAY_API_KEY", "").strip() or None
            api_key_param = os.getenv("GOOGLE_PLAY_API_KEY_PARAM", "key").strip()
            default_country = os.getenv("GOOGLE_PLAY_DEFAULT_COUNTRY", "ES").strip().upper()
            default_language = os.getenv("GOOGLE_PLAY_DEFAULT_LANGUAGE", "es").strip()
            max_reviews = _env_int("GOOGLE_PLAY_MAX_REVIEWS", 200)
            scrape_timeout = _env_int("GOOGLE_PLAY_SCRAPE_TIMEOUT", 15)

            package_ids_by_geo = _get_dict_str_list_str(gp_cfg, "package_ids_by_geo")
            geo_to_gl = _get_dict_str_str(gp_cfg, "geo_to_gl")
            geo_to_hl = _get_dict_str_str(gp_cfg, "geo_to_hl")

            if api_enabled and not gp_endpoint:
                notes.append("google_play: missing GOOGLE_PLAY_API_ENDPOINT")
            if not package_ids and not package_ids_by_geo:
                notes.append("google_play: missing package_ids in config.json")
            else:
                for package_id in list(dict.fromkeys(package_ids)):
                    collector = self._build_google_play_collector(
                        api_enabled=api_enabled,
                        endpoint=gp_endpoint,
                        api_key=api_key,
                        api_key_param=api_key_param,
                        package_id=package_id,
                        country=default_country,
                        language=default_language,
                        max_reviews=max_reviews,
                        scrape_timeout=scrape_timeout,
                        geo=None,
                    )
                    if collector:
                        collectors.append(collector)

                for geo, geo_packages in package_ids_by_geo.items():
                    geo_country = geo_to_gl.get(geo, default_country)
                    geo_language = geo_to_hl.get(geo, default_language)
                    for package_id in geo_packages:
                        collector = self._build_google_play_collector(
                            api_enabled=api_enabled,
                            endpoint=gp_endpoint,
                            api_key=api_key,
                            api_key_param=api_key_param,
                            package_id=package_id,
                            country=geo_country,
                            language=geo_language,
                            max_reviews=max_reviews,
                            scrape_timeout=scrape_timeout,
                            geo=geo,
                        )
                        if collector:
                            collectors.append(collector)

        if "reddit" in sources_enabled:
            handled_sources.add("reddit")
            reddit_cfg = _as_dict(cfg.get("reddit"))
            client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
            client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
            user_agent = os.getenv("REDDIT_USER_AGENT", "global-overview-radar/0.1").strip()

            subreddits = _get_list_str(reddit_cfg, "subreddits")
            query_templates = _get_list_str(reddit_cfg, "query_templates")
            limit_per_query = _env_int("REDDIT_LIMIT_PER_QUERY", 150)

            queries = self._expand_queries(query_templates, entity_terms)

            if not client_id or not client_secret or not user_agent:
                notes.append("reddit: missing credentials envs")
            else:
                collectors.append(
                    RedditCollector(
                        client_id=client_id,
                        client_secret=client_secret,
                        user_agent=user_agent,
                        subreddits=subreddits,
                        queries=queries,
                        limit_per_query=limit_per_query,
                    )
                )

        if "twitter" in sources_enabled:
            handled_sources.add("twitter")
            bearer = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
            max_results = _env_int("TWITTER_MAX_RESULTS", 100)

            queries = self._build_search_queries(
                entity_terms,
                segment_terms,
                segment_mode,
                include_unquoted=True,
            )
            if not bearer:
                notes.append("twitter: missing TWITTER_BEARER_TOKEN")
            else:
                collectors.append(TwitterCollector(bearer, queries, max_results=max_results))

        if "news" in sources_enabled:
            handled_sources.add("news")
            news_cfg = _as_dict(cfg.get("news"))
            news_rss_urls = _get_list_str_or_dict(news_cfg, "rss_urls")
            rss_query_enabled = _env_bool(os.getenv("NEWS_RSS_QUERY_ENABLED", "true"))
            rss_geo_map = _get_dict_str_dict_str(news_cfg, "rss_geo_map")

            api_key = os.getenv("NEWS_API_KEY", "").strip()
            language = os.getenv("NEWS_LANG", "es").strip()
            max_articles_default = _env_int("REPUTATION_DEFAULT_MAX_ITEMS", 1200)
            max_articles = _env_int("NEWS_MAX_ARTICLES", max_articles_default)
            sources = os.getenv("NEWS_SOURCES", "").strip() or None
            news_endpoint = os.getenv("NEWS_API_ENDPOINT", "").strip() or None
            rss_only = _env_bool(os.getenv("NEWS_RSS_ONLY", "true"))

            queries = self._build_search_queries(
                entity_terms,
                segment_terms,
                segment_mode,
                include_unquoted=True,
            )
            rss_sources = list(news_rss_urls)
            if rss_query_enabled:
                rss_sources.extend(
                    self._build_rss_queries("news", cfg, rss_geo_map, segment_terms, segment_mode)
                )
            rss_sources = self._limit_rss_sources(rss_sources, "NEWS_MAX_RSS_URLS", notes)

            if api_key == "" and len(rss_sources) == 0:
                notes.append("news: missing NEWS_API_KEY and rss_urls")
            else:
                collectors.append(
                    NewsCollector(
                        api_key=api_key,
                        queries=queries,
                        language=language,
                        max_articles=max_articles,
                        sources=sources,
                        endpoint=news_endpoint,
                        rss_urls=rss_sources,
                        rss_only=rss_only,
                        filter_terms=entity_terms,
                    )
                )

        if "newsapi" in sources_enabled:
            handled_sources.add("newsapi")
            api_key = os.getenv("NEWSAPI_API_KEY", "").strip()
            language = _env_str("NEWSAPI_LANGUAGE", _env_str("NEWS_LANG", "es"))
            max_articles_default = _env_int("REPUTATION_DEFAULT_MAX_ITEMS", 1200)
            max_articles = _env_int("NEWSAPI_MAX_ARTICLES", max_articles_default)
            sources = os.getenv("NEWSAPI_SOURCES", "").strip() or None
            domains = os.getenv("NEWSAPI_DOMAINS", "").strip() or None
            raw_sort_by = os.getenv("NEWSAPI_SORT_BY")
            sort_by = "publishedAt" if raw_sort_by is None else raw_sort_by.strip() or None
            raw_search_in = os.getenv("NEWSAPI_SEARCH_IN")
            search_in = (
                "title,description" if raw_search_in is None else raw_search_in.strip() or None
            )
            newsapi_endpoint = os.getenv("NEWSAPI_ENDPOINT", "").strip() or None

            queries = self._build_search_queries(
                entity_terms,
                segment_terms,
                segment_mode,
                include_unquoted=True,
            )
            if api_key == "":
                notes.append("newsapi: missing NEWSAPI_API_KEY")
            else:
                collectors.append(
                    NewsApiCollector(
                        api_key=api_key,
                        queries=queries,
                        language=language,
                        max_articles=max_articles,
                        sources=sources,
                        domains=domains,
                        sort_by=sort_by,
                        search_in=search_in,
                        endpoint=newsapi_endpoint,
                    )
                )

        if "gdelt" in sources_enabled:
            handled_sources.add("gdelt")
            max_items_default = _env_int("REPUTATION_DEFAULT_MAX_ITEMS", 1200)
            max_items = _env_int("GDELT_MAX_ITEMS", max_items_default)
            max_records = _env_int("GDELT_MAX_RECORDS", 250)
            timespan = os.getenv("GDELT_TIMESPAN", "7d").strip() or None
            sort = os.getenv("GDELT_SORT", "HybridRel").strip() or "HybridRel"
            query_suffix = os.getenv("GDELT_QUERY_SUFFIX", "").strip() or None
            start_datetime = os.getenv("GDELT_START_DATETIME", "").strip() or None
            end_datetime = os.getenv("GDELT_END_DATETIME", "").strip() or None

            queries = self._build_search_queries(
                entity_terms,
                segment_terms,
                segment_mode,
                include_unquoted=True,
            )
            if not queries:
                notes.append("gdelt: missing queries")
            else:
                collectors.append(
                    GdeltCollector(
                        queries=queries,
                        max_records=max_records,
                        max_items=max_items,
                        timespan=timespan,
                        sort=sort,
                        query_suffix=query_suffix,
                        start_datetime=start_datetime,
                        end_datetime=end_datetime,
                    )
                )

        if "guardian" in sources_enabled:
            handled_sources.add("guardian")
            api_key = os.getenv("GUARDIAN_API_KEY", "").strip()
            max_items_default = _env_int("REPUTATION_DEFAULT_MAX_ITEMS", 1200)
            max_items = _env_int("GUARDIAN_MAX_ITEMS", max_items_default)
            page_size = _env_int("GUARDIAN_PAGE_SIZE", 50)
            order_by = os.getenv("GUARDIAN_ORDER_BY", "newest").strip() or "newest"
            show_fields = os.getenv("GUARDIAN_SHOW_FIELDS", "").strip() or None
            from_date = os.getenv("GUARDIAN_FROM_DATE", "").strip() or None
            to_date = os.getenv("GUARDIAN_TO_DATE", "").strip() or None
            section = os.getenv("GUARDIAN_SECTION", "").strip() or None
            tag = os.getenv("GUARDIAN_TAG", "").strip() or None

            queries = self._build_search_queries(
                entity_terms,
                segment_terms,
                segment_mode,
                include_unquoted=True,
            )
            if api_key == "":
                notes.append("guardian: missing GUARDIAN_API_KEY")
            else:
                collectors.append(
                    GuardianCollector(
                        api_key=api_key,
                        queries=queries,
                        max_items=max_items,
                        page_size=page_size,
                        order_by=order_by,
                        show_fields=show_fields,
                        from_date=from_date,
                        to_date=to_date,
                        section=section,
                        tag=tag,
                    )
                )

        if "forums" in sources_enabled:
            handled_sources.add("forums")
            forums_cfg = _as_dict(cfg.get("forums"))
            rss_urls = _get_list_str_or_dict(forums_cfg, "rss_urls")
            rss_query_enabled = _env_bool(os.getenv("FORUMS_RSS_QUERY_ENABLED", "true"))

            scraping_enabled = _env_bool(os.getenv("FORUMS_SCRAPING", "true"))
            max_items = _env_int("FORUMS_MAX_THREADS", 200)
            rss_sources = list(rss_urls)
            if rss_query_enabled:
                rss_sources.extend(
                    self._build_rss_queries(
                        "forums", cfg, news_geo_map, segment_terms, segment_mode
                    )
                )
            rss_sources = self._limit_rss_sources(rss_sources, "FORUMS_MAX_RSS_URLS", notes)

            if not rss_sources:
                notes.append("forums: missing rss_urls in config.json")
            else:
                collectors.append(
                    ForumsCollector(
                        rss_urls=rss_sources,
                        keywords=entity_terms,
                        scraping_enabled=scraping_enabled,
                        max_items=max_items,
                    )
                )

        if "blogs" in sources_enabled:
            handled_sources.add("blogs")
            blogs_cfg = _as_dict(cfg.get("blogs"))
            rss_urls = _get_list_str_or_dict(blogs_cfg, "rss_urls")
            rss_query_enabled = _env_bool(os.getenv("BLOGS_RSS_QUERY_ENABLED", "true"))

            rss_only = _env_bool(os.getenv("BLOGS_RSS_ONLY", "true"))
            max_items = _env_int("BLOGS_MAX_ITEMS", 200)
            rss_sources = list(rss_urls)
            if rss_query_enabled:
                rss_sources.extend(
                    self._build_rss_queries("blogs", cfg, news_geo_map, segment_terms, segment_mode)
                )
            rss_sources = self._limit_rss_sources(rss_sources, "BLOGS_MAX_RSS_URLS", notes)

            if not rss_only:
                notes.append("blogs: rss_only=false not supported")
            elif not rss_sources:
                notes.append("blogs: missing rss_urls in config.json")
            else:
                collectors.append(
                    BlogsCollector(
                        rss_urls=rss_sources,
                        keywords=entity_terms,
                        max_items=max_items,
                    )
                )

        if "trustpilot" in sources_enabled:
            handled_sources.add("trustpilot")
            trust_cfg = _as_dict(cfg.get("trustpilot"))
            rss_urls = _get_list_str_or_dict(trust_cfg, "rss_urls")
            rss_query_enabled = _env_bool(os.getenv("TRUSTPILOT_RSS_QUERY_ENABLED", "true"))

            scraping_enabled = _env_bool(os.getenv("TRUSTPILOT_SCRAPING", "true"))
            max_items = _env_int("TRUSTPILOT_MAX_ITEMS", 200)
            rss_sources = list(rss_urls)
            if rss_query_enabled:
                rss_sources.extend(
                    self._build_rss_queries(
                        "trustpilot", cfg, news_geo_map, segment_terms, segment_mode
                    )
                )
            rss_sources = self._limit_rss_sources(rss_sources, "TRUSTPILOT_MAX_RSS_URLS", notes)

            if not rss_sources:
                notes.append("trustpilot: missing rss_urls in config.json")
            else:
                collectors.append(
                    TrustpilotCollector(
                        rss_urls=rss_sources,
                        keywords=entity_terms,
                        scraping_enabled=scraping_enabled,
                        max_items=max_items,
                    )
                )

        if "google_reviews" in sources_enabled:
            handled_sources.add("google_reviews")
            google_cfg = _as_dict(cfg.get("google_reviews"))
            api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
            cfg_place_ids = _get_list_str(google_cfg, "place_ids")
            place_ids = list(cfg_place_ids)
            max_reviews = _env_int("GOOGLE_MAX_REVIEWS", 200)

            place_ids = list(dict.fromkeys(place_ids))
            if api_key == "" or len(place_ids) == 0:
                notes.append("google_reviews: missing API key or place_ids in config.json")
            else:
                for place_id_value in place_ids:
                    collectors.append(
                        GoogleReviewsCollector(
                            api_key=api_key,
                            place_id=place_id_value,
                            max_reviews=max_reviews,
                        )
                    )

        if "youtube" in sources_enabled:
            handled_sources.add("youtube")
            api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
            max_results = _env_int("YOUTUBE_MAX_RESULTS", 50)

            queries = self._build_search_queries(
                entity_terms,
                segment_terms,
                segment_mode,
                include_unquoted=True,
            )
            if api_key == "":
                notes.append("youtube: missing YOUTUBE_API_KEY")
            else:
                collectors.append(
                    YouTubeCollector(
                        api_key=api_key,
                        queries=queries,
                        max_results=max_results,
                    )
                )

        if "downdetector" in sources_enabled:
            handled_sources.add("downdetector")
            down_cfg = _as_dict(cfg.get("downdetector"))
            rss_urls = _get_list_str_or_dict(down_cfg, "rss_urls")
            rss_query_enabled = _env_bool(os.getenv("DOWNDETECTOR_RSS_QUERY_ENABLED", "true"))

            scraping_enabled = _env_bool(os.getenv("DOWNDETECTOR_SCRAPING", "true"))
            max_items = _env_int("DOWNDETECTOR_MAX_ITEMS", 200)
            rss_sources = list(rss_urls)
            if rss_query_enabled:
                rss_sources.extend(
                    self._build_rss_queries(
                        "downdetector", cfg, news_geo_map, segment_terms, segment_mode
                    )
                )
            rss_sources = self._limit_rss_sources(rss_sources, "DOWNDETECTOR_MAX_RSS_URLS", notes)

            if not rss_sources:
                notes.append("downdetector: missing rss_urls in config.json")
            else:
                collectors.append(
                    DowndetectorCollector(
                        rss_urls=rss_sources,
                        keywords=entity_terms,
                        scraping_enabled=scraping_enabled,
                        max_items=max_items,
                    )
                )

        for source in sources_enabled:
            if source not in handled_sources:
                notes.append(f"{source}: collector not implemented")

        return collectors, notes

    @staticmethod
    def _load_keywords(cfg: dict[str, Any]) -> list[str]:
        return _get_list_str(cfg, "keywords")

    @staticmethod
    def _load_segment_terms(cfg: dict[str, Any]) -> list[str]:
        return [t.strip() for t in cfg.get("segment_terms", []) if isinstance(t, str) and t.strip()]

    @staticmethod
    def _segment_query_mode(cfg: dict[str, Any]) -> str:
        env_value = os.getenv("REPUTATION_SEGMENT_QUERY_MODE", "").strip()
        if env_value:
            return env_value.lower()
        return str(cfg.get("segment_query_mode", "broad")).strip().lower()

    @staticmethod
    def _expand_queries(templates: list[str], keywords: list[str]) -> list[str]:
        if not templates:
            return keywords
        queries: list[str] = []
        for keyword in keywords:
            for template in templates:
                queries.append(template.replace("{actor}", keyword))
        return list(dict.fromkeys([q for q in queries if q]))

    @staticmethod
    def _limit_rss_sources(
        rss_sources: list[dict[str, str] | str],
        env_key: str,
        notes: list[str],
    ) -> list[dict[str, str] | str]:
        raw = os.getenv(env_key, "").strip()
        if not raw:
            default_limit = DEFAULT_RSS_URL_LIMITS.get(env_key)
            if not default_limit:
                return rss_sources
            limit = default_limit
            if len(rss_sources) > limit:
                notes.append(f"{env_key}: capped rss_urls {len(rss_sources)} -> {limit}")
                return rss_sources[:limit]
            return rss_sources
        try:
            limit = int(raw)
        except ValueError:
            notes.append(f"{env_key}: invalid value '{raw}'")
            return rss_sources
        if limit <= 0:
            return rss_sources
        if len(rss_sources) > limit:
            notes.append(f"{env_key}: capped rss_urls {len(rss_sources)} -> {limit}")
            return rss_sources[:limit]
        return rss_sources

    @staticmethod
    def _build_appstore_collector(
        api_enabled: bool,
        country: str,
        app_id: str,
        max_reviews: int,
        scrape_timeout: int,
        geo: str | None,
    ) -> ReputationCollector:
        if api_enabled:
            return AppStoreCollector(
                country=country,
                app_id=app_id,
                max_reviews=max_reviews,
                geo=geo,
            )
        return AppStoreScraperCollector(
            country=country,
            app_id=app_id,
            max_reviews=max_reviews,
            geo=geo,
            timeout=scrape_timeout,
        )

    @staticmethod
    def _build_google_play_collector(
        api_enabled: bool,
        endpoint: str,
        api_key: str | None,
        api_key_param: str,
        package_id: str,
        country: str,
        language: str,
        max_reviews: int,
        scrape_timeout: int,
        geo: str | None,
    ) -> ReputationCollector | None:
        if api_enabled:
            if not endpoint:
                return None
            return GooglePlayApiCollector(
                endpoint=endpoint,
                api_key=api_key,
                api_key_param=api_key_param,
                package_id=package_id,
                country=country,
                language=language,
                max_reviews=max_reviews,
                geo=geo,
            )
        return GooglePlayScraperCollector(
            package_id=package_id,
            country=country,
            language=language,
            max_reviews=max_reviews,
            geo=geo,
            timeout=scrape_timeout,
        )

    @staticmethod
    def _default_keyword_queries(keywords: list[str], include_unquoted: bool = False) -> list[str]:
        if not keywords:
            return []
        queries = [f'"{keyword}"' for keyword in keywords if keyword]
        if include_unquoted:
            queries.extend([keyword for keyword in keywords if keyword])
        return list(dict.fromkeys([q for q in queries if q]))

    @staticmethod
    def _segment_expression(segment_terms: list[str]) -> str:
        terms: list[str] = []
        for term in segment_terms:
            if not term:
                continue
            if " " in term:
                terms.append(f'"{term}"')
            else:
                terms.append(term)
        return " OR ".join(list(dict.fromkeys([t for t in terms if t])))

    @staticmethod
    def _term_has_business_hint(term: str) -> bool:
        normalized = normalize_text(term)
        return any(hint in normalized for hint in _BUSINESS_HINTS)

    def _build_search_queries(
        self,
        terms: list[str],
        segment_terms: list[str],
        segment_mode: str,
        include_unquoted: bool = False,
    ) -> list[str]:
        if not terms:
            return []
        segment_expr = self._segment_expression(segment_terms)
        queries: list[str] = []
        for term in terms:
            cleaned = term.strip()
            if not cleaned:
                continue
            has_hint = self._term_has_business_hint(cleaned)
            mode = segment_mode or "broad"
            if mode not in {"broad", "strict"}:
                mode = "broad"

            if mode == "broad" or has_hint or not segment_expr:
                queries.append(f'"{cleaned}"')
                if include_unquoted:
                    queries.append(cleaned)
            if segment_expr:
                queries.append(f'"{cleaned}" ({segment_expr})')
                if include_unquoted and (mode == "broad" or has_hint):
                    queries.append(f"{cleaned} ({segment_expr})")
        return list(dict.fromkeys([q for q in queries if q]))

    @staticmethod
    def _load_entity_terms(cfg: dict[str, Any], keywords: list[str]) -> list[str]:
        terms = list(keywords)
        terms.extend(actor_principal_terms(cfg))
        global_actors = cfg.get("otros_actores_globales") or []
        actors_by_geo = cfg.get("otros_actores_por_geografia") or {}
        actors_aliases = cfg.get("otros_actores_aliases") or {}
        for name in global_actors:
            if isinstance(name, str):
                terms.append(name.strip())
        if isinstance(actors_by_geo, dict):
            for _, names in actors_by_geo.items():
                if not isinstance(names, list):
                    continue
                for name in names:
                    if isinstance(name, str):
                        terms.append(name.strip())
        if isinstance(actors_aliases, dict):
            for canonical, aliases in actors_aliases.items():
                if isinstance(canonical, str):
                    terms.append(canonical.strip())
                if isinstance(aliases, list):
                    for alias in aliases:
                        if isinstance(alias, str):
                            terms.append(alias.strip())
        return list(dict.fromkeys([t for t in terms if t]))

    @staticmethod
    def _normalize_site_domain(domain: str) -> str:
        cleaned = domain.strip().lower()
        for prefix in ("https://", "http://"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
                break
        if cleaned.startswith("www."):
            cleaned = cleaned[4:]
        return cleaned.strip("/")

    @classmethod
    def _build_source_geo_map(cls, cfg: dict[str, Any], geos: list[str]) -> dict[str, str]:
        news_cfg = cfg.get("news") or {}
        site_sources = news_cfg.get("site_sources_by_geo") or {}
        if not site_sources or not geos:
            return {}
        mapping: dict[str, str] = {}
        for geo in geos:
            entries = cls._flatten_site_sources(site_sources, geo)
            for entry in entries:
                domain = cls._normalize_site_domain(entry.get("domain", ""))
                geo_value = entry.get("geo") or geo
                if not domain or not geo_value:
                    continue
                mapping.setdefault(domain, geo_value)
        return mapping

    @staticmethod
    def _detect_geo_in_text(
        text: str, geos: list[str], geo_aliases: dict[str, list[str]]
    ) -> str | None:
        if not text or not geos:
            return None
        normalized = normalize_text(text)
        tokens = set(normalized.split())
        for geo in geos:
            geo_norm = normalize_text(geo)
            if geo_norm and geo_norm in normalized:
                return geo
            aliases = geo_aliases.get(geo, [])
            for alias in aliases:
                alias_norm = normalize_text(alias)
                if not alias_norm:
                    continue
                if len(alias_norm) <= 3:
                    if alias_norm in tokens:
                        return geo
                    continue
                if alias_norm in normalized:
                    return geo
        return None

    @staticmethod
    def _geo_aliases_from_cfg(cfg: dict[str, Any]) -> dict[str, list[str]]:
        geos = [g.strip() for g in cfg.get("geografias", []) if isinstance(g, str) and g.strip()]
        raw_aliases = cfg.get("geografias_aliases") or {}
        if not geos and isinstance(raw_aliases, dict):
            geos = [g.strip() for g in raw_aliases if isinstance(g, str) and g.strip()]
        result: dict[str, list[str]] = {}
        for geo in geos:
            aliases: list[str] = []
            if isinstance(raw_aliases, dict):
                values = raw_aliases.get(geo, [])
                if isinstance(values, list):
                    aliases.extend([a.strip() for a in values if isinstance(a, str) and a.strip()])
            aliases.append(geo)
            result[geo] = list(dict.fromkeys([a for a in aliases if a]))
        return result

    @staticmethod
    def _name_has_geo(name: str, geo: str, geo_aliases: dict[str, list[str]]) -> bool:
        if not name or not geo:
            return False
        aliases = geo_aliases.get(geo, [])
        if not aliases:
            return False
        normalized = normalize_text(name)
        if not normalized:
            return False
        tokens = set(normalized.split())
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if not alias_norm:
                continue
            if len(alias_norm) <= 3:
                if alias_norm in tokens:
                    return True
            elif alias_norm in normalized:
                return True
        return False

    @staticmethod
    def _name_conflicts_geo(name: str, geo: str, geo_aliases: dict[str, list[str]]) -> bool:
        if not name or not geo_aliases:
            return False
        normalized = normalize_text(name)
        if not normalized:
            return False
        tokens = set(normalized.split())
        for other_geo, aliases in geo_aliases.items():
            if other_geo == geo:
                continue
            for alias in aliases:
                alias_norm = normalize_text(alias)
                if not alias_norm:
                    continue
                if len(alias_norm) <= 3:
                    if alias_norm in tokens:
                        return True
                elif alias_norm in normalized:
                    return True
        return False

    @classmethod
    def _infer_geo_from_source(
        cls, item: ReputationItem, source_geo_map: dict[str, str]
    ) -> str | None:
        if not source_geo_map:
            return None
        signals = item.signals or {}
        candidates: list[str] = []

        site_value = signals.get("site")
        if isinstance(site_value, str) and site_value:
            candidates.append(site_value)

        source_value = signals.get("source")
        if isinstance(source_value, str) and "." in source_value:
            candidates.append(source_value)

        if item.url:
            candidates.append(item.url)

        for field in (item.title, item.text):
            if field:
                candidates.extend(cls._extract_domains(field, source_geo_map))

        for candidate in candidates:
            domain = cls._normalize_site_domain(cls._extract_domain(candidate))
            if not domain:
                domain = cls._normalize_site_domain(candidate)
            if not domain:
                continue
            geo = source_geo_map.get(domain)
            if geo:
                return geo
        return None

    @staticmethod
    def _extract_domain(value: str) -> str:
        if not value:
            return ""
        try:
            parsed = urlparse(value)
            if parsed.netloc:
                return parsed.netloc
        except Exception:
            pass
        try:
            parsed = urlparse(f"http://{value}")
            return parsed.netloc
        except Exception:
            return ""

    @staticmethod
    def _extract_domains(text: str, source_geo_map: dict[str, str]) -> list[str]:
        if not text or not source_geo_map:
            return []
        matches = re.findall(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", text.lower())
        if not matches:
            return []
        results: list[str] = []
        for match in matches:
            cleaned = match.strip(".:,;")
            if cleaned in source_geo_map:
                results.append(cleaned)
            elif cleaned.startswith("www.") and cleaned[4:] in source_geo_map:
                results.append(cleaned[4:])
        return results

    @classmethod
    def _flatten_site_sources(cls, site_sources: object, geo: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []

        def add_domain(domain: object, category: str | None, geo_value: str | None) -> None:
            if not isinstance(domain, str):
                return
            normalized = cls._normalize_site_domain(domain)
            if not normalized:
                return
            entries.append(
                {
                    "domain": normalized,
                    "category": category or "",
                    "geo": geo_value or "",
                }
            )

        def consume(value: object, geo_value: str | None) -> None:
            if isinstance(value, dict):
                for category, domains in value.items():
                    if isinstance(domains, list):
                        for domain in domains:
                            add_domain(domain, str(category) if category else "", geo_value)
            elif isinstance(value, list):
                for domain in value:
                    add_domain(domain, "", geo_value)

        if isinstance(site_sources, dict):
            consume(site_sources.get(geo), geo)
            consume(site_sources.get("global"), "")
            consume(site_sources.get("all"), "")
        else:
            consume(site_sources, geo)

        seen: set[tuple[str, str, str]] = set()
        unique: list[dict[str, str]] = []
        for entry in entries:
            key = (entry.get("domain", ""), entry.get("category", ""), entry.get("geo", ""))
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        return unique

    @staticmethod
    def _round_robin(items: list[dict[str, str]], key: str) -> list[dict[str, str]]:
        buckets: dict[str, list[dict[str, str]]] = {}
        order: list[str] = []
        for item in items:
            bucket_key = item.get(key, "") if key else ""
            if bucket_key not in buckets:
                buckets[bucket_key] = []
                order.append(bucket_key)
            buckets[bucket_key].append(item)
        result: list[dict[str, str]] = []
        remaining = True
        while remaining:
            remaining = False
            for bucket_key in order:
                bucket = buckets.get(bucket_key) or []
                if not bucket:
                    continue
                result.append(bucket.pop(0))
                remaining = True
        return result

    @classmethod
    def _round_robin_geo_entity(
        cls,
        items: list[dict[str, str]],
        geo_order: list[str] | None = None,
    ) -> list[dict[str, str]]:
        if not items:
            return items
        buckets: dict[str, list[dict[str, str]]] = {}
        seen_geo: list[str] = []
        for item in items:
            geo_value = item.get("geo", "") if item else ""
            if geo_value not in buckets:
                buckets[geo_value] = []
                seen_geo.append(geo_value)
            buckets[geo_value].append(item)

        ordered_geos = geo_order or seen_geo
        interleaved: list[dict[str, str]] = []
        for geo_value in ordered_geos:
            bucket = buckets.get(geo_value)
            if not bucket:
                continue
            interleaved.extend(cls._round_robin(bucket, "entity"))

        return cls._round_robin(interleaved, "geo")

    def _build_rss_queries(
        self,
        source_key: str,
        cfg: dict[str, Any],
        geo_map: dict[str, dict[str, str]] | None,
        segment_terms: list[str],
        segment_mode: str,
        only_geos: set[str] | None = None,
        only_entities: set[str] | None = None,
    ) -> list[dict[str, str]]:
        src_cfg = cfg.get(source_key) or {}
        templates = src_cfg.get("rss_query_templates") or []
        if not templates:
            return []
        segment_mode_override = str(src_cfg.get("rss_query_segment_mode") or "").strip().lower()
        if segment_mode_override in {"broad", "strict"}:
            segment_mode = segment_mode_override
        prefix = source_key.upper()
        default_geo_mode = "optional"
        geo_mode = str(src_cfg.get("rss_query_geo_mode") or "").strip().lower()
        if not geo_mode:
            geo_mode = _env_str(f"{prefix}_RSS_QUERY_GEO_MODE", default_geo_mode).lower()
        if geo_mode not in {"required", "optional", "none"}:
            geo_mode = "optional"
        default_order = "round_robin_geo_entity" if source_key == "news" else "as_is"
        query_order = str(src_cfg.get("rss_query_order") or "").strip().lower()
        if not query_order:
            query_order = _env_str(f"{prefix}_RSS_QUERY_ORDER", default_order).lower()
        if query_order not in {
            "as_is",
            "round_robin_geo",
            "round_robin_entity",
            "round_robin_geo_entity",
        }:
            query_order = "as_is"
        default_limits = DEFAULT_NEWS_RSS_LIMITS if prefix == "NEWS" else {}
        rss_query_max_total = _config_int(src_cfg.get("rss_query_max_total"), 0)
        if rss_query_max_total <= 0:
            rss_query_max_total = _env_int(
                f"{prefix}_RSS_QUERY_MAX_TOTAL",
                int(default_limits.get("max_total", 0)),
            )
        rss_query_max_per_geo = _config_int(src_cfg.get("rss_query_max_per_geo"), 0)
        if rss_query_max_per_geo <= 0:
            rss_query_max_per_geo = _env_int(
                f"{prefix}_RSS_QUERY_MAX_PER_GEO",
                int(default_limits.get("max_per_geo", 0)),
            )
        rss_query_max_per_entity = _config_int(src_cfg.get("rss_query_max_per_entity"), 0)
        if rss_query_max_per_entity <= 0:
            rss_query_max_per_entity = _env_int(
                f"{prefix}_RSS_QUERY_MAX_PER_ENTITY",
                int(default_limits.get("max_per_entity", 0)),
            )

        geo_params_map = src_cfg.get("rss_geo_map") or geo_map or {}
        source_terms = [
            t for t in src_cfg.get("query_terms", []) if isinstance(t, str) and t.strip()
        ]
        segment_terms_local = list(dict.fromkeys([*segment_terms, *source_terms]))
        actors_by_geo = cfg.get("otros_actores_por_geografia") or {}
        geo_aliases = self._geo_aliases_from_cfg(cfg)
        global_actors = cfg.get("otros_actores_globales") or []
        keywords = self._load_keywords(cfg)
        principal_terms = actor_principal_terms(cfg)
        for term in keywords:
            if term and term not in principal_terms:
                principal_terms.append(term)

        aliases_map = build_actor_aliases_by_canonical(cfg)
        alias_lookup = build_actor_alias_map(cfg)
        principal_canonicals = set(actor_principal_canonicals(cfg))
        principal_keys = {normalize_text(term) for term in principal_terms if term}
        only_entities_expanded: set[str] | None = None
        include_principal_terms = True
        if only_entities:
            expanded: set[str] = set()
            include_principal = False
            for name in only_entities:
                cleaned = name.strip()
                if not cleaned:
                    continue
                expanded.add(cleaned)
                canonical = alias_lookup.get(normalize_text(cleaned))
                if canonical:
                    expanded.add(canonical)
                    for alias in aliases_map.get(canonical, []):
                        expanded.add(alias)
                    if canonical in principal_canonicals:
                        include_principal = True
                if normalize_text(cleaned) in principal_keys:
                    include_principal = True
            if include_principal:
                expanded.update(principal_terms)
            include_principal_terms = include_principal
            only_entities_expanded = expanded
        geo_entities: dict[str, list[str]] = {}
        if isinstance(actors_by_geo, dict):
            for geo, actors in actors_by_geo.items():
                if only_geos and geo not in only_geos:
                    continue
                names = list(actors) if isinstance(actors, list) else []
                if isinstance(global_actors, list):
                    names.extend(global_actors)
                if not only_entities_expanded or include_principal_terms:
                    names.extend(principal_terms)
                alias_names: list[str] = []
                for name in names:
                    if not isinstance(name, str):
                        continue
                    for alias in aliases_map.get(name, []) or []:
                        if isinstance(alias, str) and alias.strip():
                            alias_names.append(alias.strip())
                names.extend(alias_names)
                cleaned_names = [n.strip() for n in names if isinstance(n, str) and n.strip()]
                cleaned_names = [
                    n for n in cleaned_names if not self._name_conflicts_geo(n, geo, geo_aliases)
                ]
                if only_entities_expanded is not None:
                    cleaned_names = [n for n in cleaned_names if n in only_entities_expanded]
                geo_entities[geo] = list(dict.fromkeys(cleaned_names))

        sources: list[dict[str, str]] = []
        for geo, names in geo_entities.items():
            geo_params = geo_params_map.get(geo, {}) if isinstance(geo_params_map, dict) else {}
            if geo_mode == "required" and not geo_params:
                continue
            for name in names:
                if not name.strip():
                    continue
                base_queries = self._build_search_queries(
                    [name],
                    segment_terms_local,
                    segment_mode,
                    include_unquoted=True,
                )
                for base_query in base_queries:
                    query_variants: list[tuple[str, str | None]] = []
                    name_has_geo = self._name_has_geo(name, geo, geo_aliases)
                    if geo_mode in {"required", "optional"} and not name_has_geo:
                        query_variants.append((f'{base_query} "{geo}"', geo))
                    if geo_mode in {"none", "optional"}:
                        query_variants.append((base_query, None))
                    for query, geo_value in query_variants:
                        encoded_query = quote_plus(query)
                        for template in templates:
                            url = (
                                template.replace("{query_raw}", query)
                                .replace("{query}", encoded_query)
                                .replace("{hl}", str(geo_params.get("hl", "")))
                                .replace("{gl}", str(geo_params.get("gl", "")))
                                .replace("{ceid}", str(geo_params.get("ceid", "")))
                            )
                            if url:
                                sources.append(
                                    {
                                        "url": url,
                                        "geo": geo_value or "",
                                        "entity": name,
                                        "query": query,
                                    }
                                )

        site_sources = src_cfg.get("site_sources_by_geo") or {}
        site_query_enabled = _env_bool(
            os.getenv("NEWS_SITE_QUERY_ENABLED", "true" if source_key == "news" else "false")
        )
        if site_query_enabled and site_sources:
            site_geo_mode = _env_str("NEWS_SITE_QUERY_GEO_MODE", "none").strip().lower()
            if site_geo_mode not in {"required", "optional", "none"}:
                site_geo_mode = "none"
            site_query_mode = (
                _env_str("NEWS_SITE_QUERY_MODE", segment_mode or "broad").strip().lower()
            )
            if site_query_mode not in {"broad", "strict"}:
                site_query_mode = "broad"
            site_include_unquoted = _env_bool(
                os.getenv("NEWS_SITE_QUERY_INCLUDE_UNQUOTED", "false")
            )
            site_max_per_geo = _env_int("NEWS_SITE_QUERY_MAX_PER_GEO", 20)
            site_max_total = _env_int("NEWS_SITE_QUERY_MAX_TOTAL", 800)
            site_per_site = _env_int("NEWS_SITE_QUERY_PER_SITE", 3)
            category_terms_map = src_cfg.get("site_query_terms_by_category") or {}

            total_added = 0
            stop_all = False
            for geo, names in geo_entities.items():
                if stop_all:
                    break
                geo_params = geo_params_map.get(geo, {}) if isinstance(geo_params_map, dict) else {}
                if site_geo_mode == "required" and not geo_params:
                    continue
                site_entries = self._flatten_site_sources(site_sources, geo)
                if not site_entries:
                    continue
                if site_max_per_geo > 0:
                    site_entries = site_entries[:site_max_per_geo]
                for site_entry in site_entries:
                    if stop_all:
                        break
                    domain = site_entry.get("domain", "")
                    if not domain:
                        continue
                    category = site_entry.get("category", "")
                    site_geo = site_entry.get("geo") or ""
                    extra_terms: list[str] = []
                    if isinstance(category_terms_map, dict) and category:
                        extra_terms = [
                            t.strip()
                            for t in category_terms_map.get(category, [])
                            if isinstance(t, str) and t.strip()
                        ]
                    segment_terms_site = list(dict.fromkeys([*segment_terms_local, *extra_terms]))
                    per_site_count = 0
                    for name in names:
                        if site_per_site > 0 and per_site_count >= site_per_site:
                            break
                        if not isinstance(name, str) or not name.strip():
                            continue
                        per_site_count += 1
                        base_queries = self._build_search_queries(
                            [name],
                            segment_terms_site,
                            site_query_mode,
                            include_unquoted=site_include_unquoted,
                        )
                        for base_query in base_queries:
                            site_query_variants: list[str] = []
                            name_has_geo = self._name_has_geo(name, geo, geo_aliases)
                            if site_geo_mode in {"required", "optional"} and not name_has_geo:
                                site_query_variants.append(f'{base_query} "{geo}" site:{domain}')
                            if site_geo_mode in {"none", "optional"}:
                                site_query_variants.append(f"{base_query} site:{domain}")
                            for query in site_query_variants:
                                encoded_query = quote_plus(query)
                                for template in templates:
                                    url = (
                                        template.replace("{query_raw}", query)
                                        .replace("{query}", encoded_query)
                                        .replace("{hl}", str(geo_params.get("hl", "")))
                                        .replace("{gl}", str(geo_params.get("gl", "")))
                                        .replace("{ceid}", str(geo_params.get("ceid", "")))
                                    )
                                    if url:
                                        sources.append(
                                            {
                                                "url": url,
                                                "geo": site_geo or geo,
                                                "entity": name,
                                                "query": query,
                                                "category": category,
                                                "site": domain,
                                            }
                                        )
                                        total_added += 1
                                        if site_max_total > 0 and total_added >= site_max_total:
                                            stop_all = True
                                            break
                                if stop_all:
                                    break
                            if stop_all:
                                break

        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for source in sources:
            url = source.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            unique.append(source)

        ordered = unique
        if query_order == "round_robin_geo":
            ordered = self._round_robin(ordered, "geo")
        elif query_order == "round_robin_entity":
            ordered = self._round_robin(ordered, "entity")
        elif query_order == "round_robin_geo_entity":
            geo_order = list(geo_entities.keys())
            if "" in {item.get("geo", "") for item in ordered} and "" not in geo_order:
                geo_order.append("")
            ordered = self._round_robin_geo_entity(ordered, geo_order)

        if (
            rss_query_max_total <= 0
            and rss_query_max_per_geo <= 0
            and rss_query_max_per_entity <= 0
        ):
            return ordered

        limited: list[dict[str, str]] = []
        geo_counts: dict[str, int] = {}
        entity_counts: dict[str, int] = {}
        for source in ordered:
            geo_value = source.get("geo", "")
            entity_value = source.get("entity", "")
            if (
                rss_query_max_per_geo > 0
                and geo_value
                and geo_counts.get(geo_value, 0) >= rss_query_max_per_geo
            ):
                continue
            if (
                rss_query_max_per_entity > 0
                and entity_value
                and entity_counts.get(entity_value, 0) >= rss_query_max_per_entity
            ):
                continue
            limited.append(source)
            if geo_value:
                geo_counts[geo_value] = geo_counts.get(geo_value, 0) + 1
            if entity_value:
                entity_counts[entity_value] = entity_counts.get(entity_value, 0) + 1
            if rss_query_max_total > 0 and len(limited) >= rss_query_max_total:
                break
        return limited


_BUSINESS_HINTS = {
    "b2b",
    "business",
    "cash",
    "cash management",
    "corporate",
    "corporativa",
    "empresa",
    "empresas",
    "empresarial",
    "negocio",
    "negocios",
    "net cash",
    "netcash",
    "pyme",
    "pymes",
    "smb",
    "sme",
}

_ACTOR_REQUIRED_SOURCES = {
    "news",
    "blogs",
    "gdelt",
    "newsapi",
    "guardian",
    "downdetector",
}


def _as_dict(value: object | None) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _get_list_str(cfg: dict[str, object], key: str) -> list[str]:
    value = cfg.get(key)
    if isinstance(value, list):
        items = cast(list[object], value)
        return [v.strip() for v in items if isinstance(v, str) and v.strip()]
    return []


def _get_list_str_or_dict(cfg: dict[str, object], key: str) -> list[dict[str, str] | str]:
    value = cfg.get(key)
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    result: list[dict[str, str] | str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            item_dict = cast(dict[str, object], item)
            filtered = {k: v for k, v in item_dict.items() if isinstance(v, str)}
            if filtered:
                result.append(filtered)
    return result


def _get_dict_str_dict_str(cfg: dict[str, object], key: str) -> dict[str, dict[str, str]]:
    value = cfg.get(key)
    if not isinstance(value, dict):
        return {}
    value_dict = cast(dict[str, object], value)
    result: dict[str, dict[str, str]] = {}
    for k, v in value_dict.items():
        if not isinstance(v, dict):
            continue
        inner = cast(dict[str, object], v)
        mapped = {ik: iv for ik, iv in inner.items() if isinstance(iv, str)}
        if mapped:
            result[k] = mapped
    return result


def _get_dict_str_list_str(cfg: dict[str, object], key: str) -> dict[str, list[str]]:
    value = cfg.get(key)
    if not isinstance(value, dict):
        return {}
    value_dict = cast(dict[str, object], value)
    result: dict[str, list[str]] = {}
    for k, v in value_dict.items():
        if not isinstance(v, list):
            continue
        items = [item.strip() for item in v if isinstance(item, str) and item.strip()]
        if items:
            result[str(k)] = items
    return result


def _get_dict_str_str(cfg: dict[str, object], key: str) -> dict[str, str]:
    value = cfg.get(key)
    if not isinstance(value, dict):
        return {}
    value_dict = cast(dict[str, object], value)
    result: dict[str, str] = {}
    for k, v in value_dict.items():
        if isinstance(v, str) and v.strip():
            result[str(k)] = v.strip()
    return result


def _fetch_appstore_rating(
    app_id: str,
    country: str,
    timeout: int,
) -> tuple[float | None, int | None, str | None, str | None] | None:
    url = f"https://itunes.apple.com/lookup?id={app_id}&country={country}"
    data = http_get_json(url, timeout=timeout)
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        return None
    rating = first.get("averageUserRating") or first.get("averageUserRatingForCurrentVersion")
    if rating is None:
        return None
    rating_value = _to_float(rating)
    if rating_value is None:
        return None
    rating_count = first.get("userRatingCount") or first.get("userRatingCountForCurrentVersion")
    count_value = _to_int(rating_count)
    url_value = first.get("trackViewUrl")
    name_value = first.get("trackName")
    return (
        rating_value,
        count_value,
        str(url_value) if isinstance(url_value, str) else None,
        (str(name_value) if isinstance(name_value, str) else None),
    )


def _fetch_google_play_rating(
    package_id: str,
    gl: str,
    hl: str,
    timeout: int,
) -> tuple[float | None, int | None, str | None, str | None] | None:
    url = f"https://play.google.com/store/apps/details?id={package_id}&hl={hl}&gl={gl}"
    html = http_get_text(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    if not html:
        return None

    rating_value = _extract_rating_value(html)
    if rating_value is None:
        return None
    rating_count = _extract_rating_count(html)
    name_value = _extract_google_play_name(html)
    return rating_value, rating_count, url, name_value


def _extract_rating_value(html: str) -> float | None:
    patterns = [
        r'itemprop="ratingValue" content="([0-9.,]+)"',
        r'"ratingValue":"([0-9.,]+)"',
        r'"ratingValue":([0-9.,]+)',
    ]
    return _extract_first_float(html, patterns)


def _extract_rating_count(html: str) -> int | None:
    patterns = [
        r'itemprop="ratingCount" content="([0-9.,]+)"',
        r'"ratingCount":"([0-9.,]+)"',
        r'"ratingCount":([0-9.,]+)',
        r'"reviewCount":"([0-9.,]+)"',
        r'"reviewCount":([0-9.,]+)',
    ]
    value = _extract_first_text(html, patterns)
    if value is None:
        return None
    cleaned = value.replace(".", "").replace(",", "").strip()
    return _to_int(cleaned)


def _extract_google_play_name(html: str) -> str | None:
    match = re.search(r'property="og:title" content="([^"]+)"', html)
    if not match:
        return None
    title = match.group(1)
    if not title:
        return None
    return title.replace(" - Apps on Google Play", "").strip()


def _extract_first_text(html: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def _extract_first_float(html: str, patterns: list[str]) -> float | None:
    value = _extract_first_text(html, patterns)
    if value is None:
        return None
    return _to_float(value)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _market_rating_key(rating: MarketRating) -> tuple[str, str, str, str, str]:
    return (
        (rating.source or "").strip().lower(),
        (rating.actor or "").strip().lower(),
        (rating.geo or "").strip().lower(),
        (rating.app_id or "").strip().lower(),
        (rating.package_id or "").strip().lower(),
    )


def _market_rating_is_newer(left: MarketRating, right: MarketRating) -> bool:
    left_ts = left.collected_at or datetime.min.replace(tzinfo=timezone.utc)
    right_ts = right.collected_at or datetime.min.replace(tzinfo=timezone.utc)
    return left_ts >= right_ts


def _market_rating_is_same(left: MarketRating, right: MarketRating) -> bool:
    if abs(left.rating - right.rating) > 0.0001:
        return False
    return left.rating_count == right.rating_count


def _env_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(env_name: str, default: int) -> int:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(env_name: str, default: str) -> str:
    raw = os.getenv(env_name, "").strip()
    return raw if raw else default


def _resolve_translation_language() -> str:
    preferred = os.getenv("NEWS_LANG", "").strip()
    if preferred:
        return preferred
    fallback = os.getenv("NEWSAPI_LANGUAGE", "").strip()
    return fallback


def _config_int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _split_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
