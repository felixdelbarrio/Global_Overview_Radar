from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, cast
from urllib.parse import quote_plus, urlparse

from reputation.actors import (
    actor_principal_canonicals,
    actor_principal_terms,
    build_actor_alias_map,
    build_actor_aliases_by_canonical,
    canonicalize_actor,
)
from reputation.collectors.appstore import AppStoreCollector
from reputation.collectors.base import ReputationCollector
from reputation.collectors.blogs import BlogsCollector
from reputation.collectors.downdetector import DowndetectorCollector
from reputation.collectors.forums import ForumsCollector
from reputation.collectors.google_reviews import GoogleReviewsCollector
from reputation.collectors.news import NewsCollector
from reputation.collectors.reddit import RedditCollector
from reputation.collectors.trustpilot import TrustpilotCollector
from reputation.collectors.twitter import TwitterCollector
from reputation.collectors.utils import normalize_text
from reputation.collectors.youtube import YouTubeCollector
from reputation.config import (
    compute_config_hash,
    effective_ttl_hours,
    load_business_config,
    settings,
)
from reputation.logging_utils import get_logger
from reputation.models import ReputationCacheDocument, ReputationCacheStats, ReputationItem
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.services.sentiment_service import ReputationSentimentService

logger = get_logger(__name__)


class ReputationIngestService:
    """Ingesta de reputación: carga config, ejecuta collectors y guarda cache."""

    def __init__(self) -> None:
        self._settings = settings
        self._repo = ReputationCacheRepo(self._settings.cache_path)

    def run(self, force: bool = False) -> ReputationCacheDocument:
        cfg = _as_dict(load_business_config())
        cfg_hash = compute_config_hash(cfg)
        ttl_hours = effective_ttl_hours(cfg)
        sources_enabled = list(self._settings.enabled_sources())
        lookback_days = _env_int("REPUTATION_LOOKBACK_DAYS", 730)
        logger.info("Reputation ingest started (force=%s)", force)
        logger.debug("Sources enabled: %s", sources_enabled)

        # Feature apagada: devolvemos doc vacío, no escribimos
        if not self._settings.reputation_enabled:
            logger.info("Reputation ingest skipped: REPUTATION_ENABLED=false")
            return self._build_empty_doc(
                cfg_hash=cfg_hash,
                sources_enabled=sources_enabled,
                note="REPUTATION_ENABLED=false",
            )

        existing = self._repo.load()

        collectors, notes = self._build_collectors(cfg, sources_enabled)

        # Reutiliza cache si aplica y no hay collectors activos
        if (
            not force
            and existing
            and existing.config_hash == cfg_hash
            and self._repo.is_fresh(ttl_hours)
            and not collectors
        ):
            cache_note = "; ".join(notes) if notes else "cache hit"
            logger.info("Reputation cache hit (%s items)", len(existing.items))
            return ReputationCacheDocument(
                generated_at=datetime.now(timezone.utc),
                config_hash=cfg_hash,
                sources_enabled=sources_enabled,
                items=existing.items,
                stats=ReputationCacheStats(count=len(existing.items), note=cache_note),
            )

        items = self._collect_items(collectors, notes)
        items = self._normalize_items(items, lookback_days)
        items = self._apply_geo_hints(cfg, items)
        items = self._apply_sentiment(cfg, items)
        items = self._balance_items(
            cfg, items, existing.items if existing else [], lookback_days, notes
        )
        merged_items = self._merge_items(existing.items if existing else [], items)
        final_note: str | None = "; ".join(notes) if notes else None

        doc = ReputationCacheDocument(
            generated_at=datetime.now(timezone.utc),
            config_hash=cfg_hash,
            sources_enabled=sources_enabled,
            items=merged_items,
            stats=ReputationCacheStats(count=len(merged_items), note=final_note),
        )

        self._repo.save(doc)
        logger.info("Reputation ingest finished (%s items)", len(merged_items))

        return doc

    @staticmethod
    def _collect_items(
        collectors: Iterable[ReputationCollector],
        notes: list[str],
    ) -> list[ReputationItem]:
        items: list[ReputationItem] = []
        for collector in collectors:
            try:
                items.extend(list(collector.collect()))
            except Exception as exc:  # pragma: no cover - defensive
                notes.append(f"{collector.source_name}: error {exc}")
                logger.warning("Collector %s failed: %s", collector.source_name, exc)
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

        for item in items:
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
        self, cfg: dict[str, Any], items: list[ReputationItem]
    ) -> list[ReputationItem]:
        keywords = self._load_keywords(cfg)
        cfg_local = dict(cfg)
        cfg_local["keywords"] = keywords
        service = ReputationSentimentService(cfg_local)
        return service.analyze_items(items)

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
        enabled = _env_bool(os.getenv("REPUTATION_BALANCE_ENABLED", "false"))
        sources = _split_csv(os.getenv("REPUTATION_BALANCE_SOURCES", "news"))
        segment_terms = _split_csv(os.getenv("REPUTATION_BALANCE_SEGMENT_TERMS", ""))

        def _env_optional(env_name: str) -> str | None:
            value = os.getenv(env_name, "").strip()
            return value or None

        return {
            "enabled": enabled,
            "min_per_geo": _env_int("REPUTATION_BALANCE_MIN_PER_GEO", 0),
            "min_per_actor": _env_int("REPUTATION_BALANCE_MIN_PER_ACTOR", 0),
            "max_passes": _env_int("REPUTATION_BALANCE_MAX_PASSES", 0),
            "max_items_per_pass": _env_int("REPUTATION_BALANCE_MAX_ITEMS_PER_PASS", 0),
            "max_queries_per_pass": _env_int("REPUTATION_BALANCE_MAX_QUERIES_PER_PASS", 0),
            "max_geos": _env_int("REPUTATION_BALANCE_MAX_GEOS", 0),
            "max_actores": _env_int("REPUTATION_BALANCE_MAX_ACTORES", 0),
            "segment_query_mode": _env_optional("REPUTATION_BALANCE_SEGMENT_QUERY_MODE"),
            "segment_terms": segment_terms,
            "rss_query_geo_mode": _env_optional("REPUTATION_BALANCE_RSS_QUERY_GEO_MODE"),
            "rss_query_order": _env_optional("REPUTATION_BALANCE_RSS_QUERY_ORDER"),
            "rss_query_max_total": _env_int("REPUTATION_BALANCE_RSS_QUERY_MAX_TOTAL", 0),
            "rss_query_max_per_geo": _env_int("REPUTATION_BALANCE_RSS_QUERY_MAX_PER_GEO", 0),
            "rss_query_max_per_entity": _env_int("REPUTATION_BALANCE_RSS_QUERY_MAX_PER_ENTITY", 0),
            "sources": sources or ["news"],
        }

    def _balance_items(
        self,
        cfg: dict[str, Any],
        items: list[ReputationItem],
        existing_items: list[ReputationItem],
        lookback_days: int,
        notes: list[str],
    ) -> list[ReputationItem]:
        balance_cfg = self._load_balance_cfg()
        if not balance_cfg.get("enabled", False):
            return items

        min_per_geo = int(balance_cfg.get("min_per_geo", 0))
        min_per_actor = int(balance_cfg.get("min_per_actor", 0))
        max_passes = int(balance_cfg.get("max_passes", 0))
        if max_passes <= 0 or (min_per_geo <= 0 and min_per_actor <= 0):
            return items

        max_items_per_pass = int(balance_cfg.get("max_items_per_pass", 0))
        if max_items_per_pass <= 0:
            max_items_per_pass = _env_int("REPUTATION_DEFAULT_MAX_ITEMS", 200)
        max_queries_per_pass = int(balance_cfg.get("max_queries_per_pass", 0))
        max_geos = int(balance_cfg.get("max_geos", 0))
        max_actores = int(balance_cfg.get("max_actores", 0))
        sources = balance_cfg.get("sources") or ["news"]

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

            country = os.getenv("APPSTORE_COUNTRY", "es").strip().lower() or "es"
            max_reviews = _env_int("APPSTORE_MAX_REVIEWS", 200)

            app_ids = list(dict.fromkeys(app_ids))
            if not app_ids:
                notes.append("appstore: missing app_ids in config.json")
            else:
                for app_id_value in app_ids:
                    collectors.append(
                        AppStoreCollector(
                            country=country,
                            app_id=app_id_value,
                            max_reviews=max_reviews,
                        )
                    )

        if "reddit" in sources_enabled:
            handled_sources.add("reddit")
            reddit_cfg = _as_dict(cfg.get("reddit"))
            client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
            client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
            user_agent = os.getenv("REDDIT_USER_AGENT", "").strip()

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
            max_articles_default = _env_int("REPUTATION_DEFAULT_MAX_ITEMS", 200)
            max_articles = _env_int("NEWS_MAX_ARTICLES", max_articles_default)
            sources = os.getenv("NEWS_SOURCES", "").strip() or None
            endpoint = os.getenv("NEWS_API_ENDPOINT", "").strip() or None
            rss_only = _env_bool(os.getenv("NEWS_RSS_ONLY", "false"))

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

            if not api_key and not rss_sources:
                notes.append("news: missing NEWS_API_KEY and rss_urls")
            else:
                collectors.append(
                    NewsCollector(
                        api_key=api_key,
                        queries=queries,
                        language=language,
                        max_articles=max_articles,
                        sources=sources,
                        endpoint=endpoint,
                        rss_urls=rss_sources,
                        rss_only=rss_only,
                        filter_terms=entity_terms,
                    )
                )

        if "forums" in sources_enabled:
            handled_sources.add("forums")
            forums_cfg = _as_dict(cfg.get("forums"))
            rss_urls = _get_list_str_or_dict(forums_cfg, "rss_urls")
            rss_query_enabled = _env_bool(os.getenv("FORUMS_RSS_QUERY_ENABLED", "true"))

            scraping_enabled = _env_bool(os.getenv("FORUMS_SCRAPING", "false"))
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

            scraping_enabled = _env_bool(os.getenv("TRUSTPILOT_SCRAPING", "false"))
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
            if not api_key or not place_ids:
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
            if not api_key:
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

            scraping_enabled = _env_bool(os.getenv("DOWNDETECTOR_SCRAPING", "false"))
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
        rss_query_max_total = _config_int(src_cfg.get("rss_query_max_total"), 0)
        if rss_query_max_total <= 0:
            rss_query_max_total = _env_int(f"{prefix}_RSS_QUERY_MAX_TOTAL", 0)
        rss_query_max_per_geo = _config_int(src_cfg.get("rss_query_max_per_geo"), 0)
        if rss_query_max_per_geo <= 0:
            rss_query_max_per_geo = _env_int(f"{prefix}_RSS_QUERY_MAX_PER_GEO", 0)
        rss_query_max_per_entity = _config_int(src_cfg.get("rss_query_max_per_entity"), 0)
        if rss_query_max_per_entity <= 0:
            rss_query_max_per_entity = _env_int(f"{prefix}_RSS_QUERY_MAX_PER_ENTITY", 0)

        geo_params_map = src_cfg.get("rss_geo_map") or geo_map or {}
        source_terms = [
            t for t in src_cfg.get("query_terms", []) if isinstance(t, str) and t.strip()
        ]
        segment_terms_local = list(dict.fromkeys([*segment_terms, *source_terms]))
        actors_by_geo = cfg.get("otros_actores_por_geografia") or {}
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
                    if geo_mode in {"required", "optional"}:
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
                            if site_geo_mode in {"required", "optional"}:
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
