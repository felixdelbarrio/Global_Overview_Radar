from __future__ import annotations

from datetime import datetime, timezone, timedelta
import os
from typing import Iterable

from reputation.config import (
    compute_config_hash,
    effective_ttl_hours,
    load_business_config,
    settings,
)
from reputation.models import ReputationCacheDocument, ReputationCacheStats, ReputationItem
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.collectors.base import ReputationCollector
from reputation.collectors.appstore import AppStoreCollector
from reputation.collectors.blogs import BlogsCollector
from reputation.collectors.downdetector import DowndetectorCollector
from reputation.collectors.forums import ForumsCollector
from reputation.collectors.google_reviews import GoogleReviewsCollector
from reputation.collectors.news import NewsCollector
from reputation.collectors.reddit import RedditCollector
from reputation.collectors.trustpilot import TrustpilotCollector
from reputation.collectors.twitter import TwitterCollector
from reputation.collectors.youtube import YouTubeCollector
from reputation.services.sentiment_service import ReputationSentimentService


class ReputationIngestService:
    """Ingesta de reputación: carga config, ejecuta collectors y guarda cache."""

    def __init__(self) -> None:
        self._settings = settings
        self._repo = ReputationCacheRepo(self._settings.cache_path)

    def run(self, force: bool = False) -> ReputationCacheDocument:
        cfg = load_business_config()
        cfg_hash = compute_config_hash(cfg)
        ttl_hours = effective_ttl_hours(cfg)
        sources_enabled = list(self._settings.enabled_sources())
        lookback_days = _env_int("REPUTATION_LOOKBACK_DAYS", 30)

        # Feature apagada: devolvemos doc vacío, no escribimos
        if not self._settings.reputation_enabled:
            return self._build_empty_doc(
                cfg_hash=cfg_hash,
                sources_enabled=sources_enabled,
                note="REPUTATION_ENABLED=false",
            )

        existing = self._repo.load()

        auto_notes = self._auto_enable_rss_sources(cfg, sources_enabled)
        collectors, notes = self._build_collectors(cfg, sources_enabled)
        notes = auto_notes + notes

        # Reutiliza cache si aplica y no hay collectors activos
        if (
            not force
            and existing
            and existing.config_hash == cfg_hash
            and self._repo.is_fresh(ttl_hours)
            and not collectors
        ):
            note = "; ".join(notes) if notes else "cache hit"
            return ReputationCacheDocument(
                generated_at=datetime.now(timezone.utc),
                config_hash=cfg_hash,
                sources_enabled=sources_enabled,
                items=existing.items,
                stats=ReputationCacheStats(count=len(existing.items), note=note),
            )

        items = self._collect_items(collectors, notes)
        items = self._normalize_items(items, lookback_days)
        items = self._apply_sentiment(cfg, items)
        merged_items = self._merge_items(existing.items if existing else [], items)
        note = "; ".join(notes) if notes else None

        doc = ReputationCacheDocument(
            generated_at=datetime.now(timezone.utc),
            config_hash=cfg_hash,
            sources_enabled=sources_enabled,
            items=merged_items,
            stats=ReputationCacheStats(count=len(merged_items), note=note),
        )

        self._repo.save(doc)

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

    @staticmethod
    def _merge_items(existing: list[ReputationItem], incoming: list[ReputationItem]) -> list[ReputationItem]:
        merged: dict[tuple[str, str], ReputationItem] = {
            (item.source, item.id): item for item in existing
        }
        for item in incoming:
            key = (item.source, item.id)
            if key not in merged:
                merged[key] = item
        return list(merged.values())

    def _apply_sentiment(self, cfg: dict, items: list[ReputationItem]) -> list[ReputationItem]:
        keywords = self._load_keywords(cfg)
        entity_terms = self._load_entity_terms(cfg, keywords)
        cfg_local = dict(cfg)
        cfg_local["keywords"] = keywords
        service = ReputationSentimentService(cfg_local)
        return service.analyze_items(items)

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
        cfg: dict,
        sources_enabled: list[str],
    ) -> tuple[list[ReputationCollector], list[str]]:
        collectors: list[ReputationCollector] = []
        notes: list[str] = []
        handled_sources: set[str] = set()
        keywords = self._load_keywords(cfg)
        entity_terms = self._load_entity_terms(cfg, keywords)

        if "appstore" in sources_enabled:
            handled_sources.add("appstore")
            appstore_cfg = cfg.get("appstore") or {}
            if not appstore_cfg.get("enabled", False):
                notes.append("appstore: disabled in config.json")
            else:
                app_id_env = appstore_cfg.get("app_id_env", "APPSTORE_APP_ID")
                country_env = appstore_cfg.get("country_env", "APPSTORE_COUNTRY")
                max_reviews_env = appstore_cfg.get("max_reviews_env", "APPSTORE_MAX_REVIEWS")

                app_id = os.getenv(app_id_env, "").strip()
                country = os.getenv(country_env, "es").strip().lower() or "es"
                max_reviews_raw = os.getenv(max_reviews_env, "200").strip()

                try:
                    max_reviews = int(max_reviews_raw)
                except ValueError:
                    max_reviews = 200
                    notes.append("appstore: invalid max_reviews env, using 200")

                if not app_id:
                    notes.append(f"appstore: missing {app_id_env}")
                else:
                    collectors.append(
                        AppStoreCollector(
                            country=country,
                            app_id=app_id,
                            max_reviews=max_reviews,
                        )
                    )

        if "reddit" in sources_enabled:
            handled_sources.add("reddit")
            reddit_cfg = cfg.get("reddit") or {}
            if not reddit_cfg.get("enabled", False):
                notes.append("reddit: disabled in config.json")
            else:
                client_id_env = reddit_cfg.get("client_id_env", "REDDIT_CLIENT_ID")
                client_secret_env = reddit_cfg.get("client_secret_env", "REDDIT_CLIENT_SECRET")
                user_agent_env = reddit_cfg.get("user_agent_env", "REDDIT_USER_AGENT")

                client_id = os.getenv(client_id_env, "").strip()
                client_secret = os.getenv(client_secret_env, "").strip()
                user_agent = os.getenv(user_agent_env, "").strip()

                subreddits = reddit_cfg.get("subreddits") or []
                query_templates = reddit_cfg.get("query_templates") or []
                limit_per_query = int(reddit_cfg.get("limit_per_query", 100))

                queries = self._expand_queries(query_templates, keywords)

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
            twitter_cfg = cfg.get("twitter") or {}
            if not twitter_cfg.get("enabled", False):
                notes.append("twitter: disabled in config.json")
            else:
                bearer_env = twitter_cfg.get("bearer_token_env", "TWITTER_BEARER_TOKEN")
                max_results_env = twitter_cfg.get("max_results_env", "TWITTER_MAX_RESULTS")

                bearer = os.getenv(bearer_env, "").strip()
                max_results = _env_int(max_results_env, 100)

                queries = self._default_keyword_queries(keywords)
                if not bearer:
                    notes.append(f"twitter: missing {bearer_env}")
                else:
                    collectors.append(TwitterCollector(bearer, queries, max_results=max_results))

        if "news" in sources_enabled:
            handled_sources.add("news")
            news_cfg = cfg.get("news") or {}
            if not news_cfg.get("enabled", False):
                notes.append("news: disabled in config.json")
            else:
                api_key_env = news_cfg.get("api_key_env", "NEWS_API_KEY")
                lang_env = news_cfg.get("lang_env", "NEWS_LANG")
                max_articles_env = news_cfg.get("max_articles_env", "NEWS_MAX_ARTICLES")
                sources_env = news_cfg.get("sources_env", "NEWS_SOURCES")
                endpoint_env = news_cfg.get("endpoint_env", "NEWS_API_ENDPOINT")
                rss_only_env = news_cfg.get("rss_only_env", "NEWS_RSS_ONLY")
                rss_urls = news_cfg.get("rss_urls") or []
                rss_query_env = os.getenv("NEWS_RSS_QUERY_ENABLED", "").strip().lower()
                rss_query_enabled = bool(news_cfg.get("rss_query_enabled", True))
                if rss_query_env:
                    rss_query_enabled = rss_query_env in {"1", "true", "yes", "y", "on"}
                rss_geo_map = news_cfg.get("rss_geo_map") or {}

                api_key = os.getenv(api_key_env, "").strip()
                language = os.getenv(lang_env, "es").strip()
                max_articles = _env_int(max_articles_env, 200)
                sources = os.getenv(sources_env, "").strip() or None
                endpoint = os.getenv(endpoint_env, "").strip() or None
                rss_only = _env_bool(os.getenv(rss_only_env, "false"))

                queries = self._default_keyword_queries(entity_terms)
                rss_sources = list(rss_urls)
                if rss_query_enabled:
                    rss_sources.extend(self._build_news_rss_queries(cfg, rss_geo_map))

                if not api_key and not rss_sources:
                    notes.append(f"news: missing {api_key_env} and rss_urls")
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
                        )
                    )

        if "forums" in sources_enabled:
            handled_sources.add("forums")
            forums_cfg = cfg.get("forums") or {}
            if not forums_cfg.get("enabled", False):
                notes.append("forums: disabled in config.json")
            else:
                scraping_env = forums_cfg.get("scraping_env", "FORUMS_SCRAPING")
                max_threads_env = forums_cfg.get("max_threads_env", "FORUMS_MAX_THREADS")
                rss_urls = forums_cfg.get("rss_urls") or []

                scraping_enabled = _env_bool(os.getenv(scraping_env, "false"))
                max_items = _env_int(max_threads_env, 200)

                if not rss_urls:
                    notes.append("forums: missing rss_urls in config.json")
                else:
                    collectors.append(
                        ForumsCollector(
                            rss_urls=rss_urls,
                            keywords=entity_terms,
                            scraping_enabled=scraping_enabled,
                            max_items=max_items,
                        )
                    )

        if "blogs" in sources_enabled:
            handled_sources.add("blogs")
            blogs_cfg = cfg.get("blogs") or {}
            if not blogs_cfg.get("enabled", False):
                notes.append("blogs: disabled in config.json")
            else:
                rss_only_env = blogs_cfg.get("rss_only_env", "BLOGS_RSS_ONLY")
                max_items_env = blogs_cfg.get("max_items_env", "BLOGS_MAX_ITEMS")
                rss_urls = blogs_cfg.get("rss_urls") or []

                rss_only = _env_bool(os.getenv(rss_only_env, "true"))
                max_items = _env_int(max_items_env, 200)

                if not rss_only:
                    notes.append("blogs: rss_only=false not supported")
                elif not rss_urls:
                    notes.append("blogs: missing rss_urls in config.json")
                else:
                    collectors.append(
                        BlogsCollector(
                            rss_urls=rss_urls,
                            keywords=entity_terms,
                            max_items=max_items,
                        )
                    )

        if "trustpilot" in sources_enabled:
            handled_sources.add("trustpilot")
            trust_cfg = cfg.get("trustpilot") or {}
            if not trust_cfg.get("enabled", False):
                notes.append("trustpilot: disabled in config.json")
            else:
                scraping_env = trust_cfg.get("scraping_env", "TRUSTPILOT_SCRAPING")
                max_items_env = trust_cfg.get("max_items_env", "TRUSTPILOT_MAX_ITEMS")
                rss_urls = trust_cfg.get("rss_urls") or []

                scraping_enabled = _env_bool(os.getenv(scraping_env, "false"))
                max_items = _env_int(max_items_env, 200)

                if not rss_urls:
                    notes.append("trustpilot: missing rss_urls in config.json")
                else:
                    collectors.append(
                        TrustpilotCollector(
                            rss_urls=rss_urls,
                            keywords=entity_terms,
                            scraping_enabled=scraping_enabled,
                            max_items=max_items,
                        )
                    )

        if "google_reviews" in sources_enabled:
            handled_sources.add("google_reviews")
            google_cfg = cfg.get("google_reviews") or {}
            if not google_cfg.get("enabled", False):
                notes.append("google_reviews: disabled in config.json")
            else:
                api_key_env = google_cfg.get("api_key_env", "GOOGLE_PLACES_API_KEY")
                place_id_env = google_cfg.get("place_id_env", "GOOGLE_PLACE_ID")
                max_reviews_env = google_cfg.get("max_reviews_env", "GOOGLE_MAX_REVIEWS")

                api_key = os.getenv(api_key_env, "").strip()
                place_id = os.getenv(place_id_env, "").strip()
                max_reviews = _env_int(max_reviews_env, 200)

                if not api_key or not place_id:
                    notes.append("google_reviews: missing API key or place id")
                else:
                    collectors.append(
                        GoogleReviewsCollector(
                            api_key=api_key,
                            place_id=place_id,
                            max_reviews=max_reviews,
                        )
                    )

        if "youtube" in sources_enabled:
            handled_sources.add("youtube")
            youtube_cfg = cfg.get("youtube") or {}
            if not youtube_cfg.get("enabled", False):
                notes.append("youtube: disabled in config.json")
            else:
                api_key_env = youtube_cfg.get("api_key_env", "YOUTUBE_API_KEY")
                max_results_env = youtube_cfg.get("max_results_env", "YOUTUBE_MAX_RESULTS")

                api_key = os.getenv(api_key_env, "").strip()
                max_results = _env_int(max_results_env, 50)

                queries = self._default_keyword_queries(keywords)
                if not api_key:
                    notes.append(f"youtube: missing {api_key_env}")
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
            down_cfg = cfg.get("downdetector") or {}
            if not down_cfg.get("enabled", False):
                notes.append("downdetector: disabled in config.json")
            else:
                scraping_env = down_cfg.get("scraping_env", "DOWNDETECTOR_SCRAPING")
                max_items_env = down_cfg.get("max_items_env", "DOWNDETECTOR_MAX_ITEMS")
                rss_urls = down_cfg.get("rss_urls") or []

                scraping_enabled = _env_bool(os.getenv(scraping_env, "false"))
                max_items = _env_int(max_items_env, 200)

                if not rss_urls:
                    notes.append("downdetector: missing rss_urls in config.json")
                else:
                    collectors.append(
                        DowndetectorCollector(
                            rss_urls=rss_urls,
                            keywords=entity_terms,
                            scraping_enabled=scraping_enabled,
                            max_items=max_items,
                        )
                    )

        for source in sources_enabled:
            if source not in handled_sources:
                notes.append(f"{source}: collector not implemented")

        return collectors, notes

    def _auto_enable_rss_sources(self, cfg: dict, sources_enabled: list[str]) -> list[str]:
        notes: list[str] = []
        rss_sources = ["news", "forums", "blogs", "trustpilot", "downdetector"]

        for source in rss_sources:
            if source in sources_enabled:
                continue
            src_cfg = cfg.get(source) or {}
            if not src_cfg.get("enabled", False):
                continue
            rss_urls = src_cfg.get("rss_urls") or []
            if not rss_urls:
                continue

            if source == "news":
                rss_only_env = src_cfg.get("rss_only_env", "NEWS_RSS_ONLY")
                if not _env_bool(os.getenv(rss_only_env, "false")):
                    continue
            elif source == "blogs":
                rss_only_env = src_cfg.get("rss_only_env", "BLOGS_RSS_ONLY")
                if not _env_bool(os.getenv(rss_only_env, "true")):
                    continue
            else:
                scraping_env = src_cfg.get("scraping_env", f"{source.upper()}_SCRAPING")
                if not _env_bool(os.getenv(scraping_env, "false")):
                    continue

            sources_enabled.append(source)
            notes.append(f"{source}: auto-enabled (rss)")

        return notes

    @staticmethod
    def _load_keywords(cfg: dict) -> list[str]:
        env_keywords = os.getenv("REPUTATION_KEYWORDS", "").strip()
        if env_keywords:
            return [k.strip() for k in env_keywords.split(",") if k.strip()]
        return [k.strip() for k in cfg.get("keywords", []) if isinstance(k, str) and k.strip()]

    @staticmethod
    def _expand_queries(templates: list[str], keywords: list[str]) -> list[str]:
        if not templates:
            return keywords
        queries: list[str] = []
        for keyword in keywords:
            for template in templates:
                queries.append(template.replace("{competidor}", keyword))
        return list(dict.fromkeys([q for q in queries if q]))

    @staticmethod
    def _default_keyword_queries(keywords: list[str]) -> list[str]:
        if not keywords:
            return []
        return [f"\"{keyword}\"" for keyword in keywords]

    @staticmethod
    def _load_entity_terms(cfg: dict, keywords: list[str]) -> list[str]:
        terms = list(keywords)
        global_competitors = cfg.get("global_competitors") or []
        competitors_by_geo = cfg.get("competidores_por_geografia") or {}
        for name in global_competitors:
            if isinstance(name, str):
                terms.append(name.strip())
        if isinstance(competitors_by_geo, dict):
            for _, names in competitors_by_geo.items():
                if not isinstance(names, list):
                    continue
                for name in names:
                    if isinstance(name, str):
                        terms.append(name.strip())
        # Garantiza BBVA como término base
        terms.append("BBVA")
        return list(dict.fromkeys([t for t in terms if t]))

    def _build_news_rss_queries(self, cfg: dict, geo_map: dict) -> list[dict[str, str]]:
        news_cfg = cfg.get("news") or {}
        templates = news_cfg.get("rss_query_templates") or []
        if not templates:
            return []

        competitors_by_geo = cfg.get("competidores_por_geografia") or {}
        global_competitors = cfg.get("global_competitors") or []
        keywords = self._load_keywords(cfg)
        bbva_terms = [k for k in keywords if "bbva" in k.lower()] or [
            "BBVA Empresas",
            "BBVA Business",
        ]

        sources: list[dict[str, str]] = []
        for geo, competitors in competitors_by_geo.items():
            geo_params = geo_map.get(geo, {})
            if not geo_params:
                continue
            names = list(competitors) if isinstance(competitors, list) else []
            if isinstance(global_competitors, list):
                names.extend(global_competitors)
            names.extend(bbva_terms)
            for name in names:
                if not isinstance(name, str) or not name.strip():
                    continue
                query = f"\"{name}\" \"{geo}\""
                for template in templates:
                    url = (
                        template.replace("{query}", query)
                        .replace("{hl}", str(geo_params.get("hl", "")))
                        .replace("{gl}", str(geo_params.get("gl", "")))
                        .replace("{ceid}", str(geo_params.get("ceid", "")))
                    )
                    if url:
                        sources.append({"url": url, "geo": geo})

        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for source in sources:
            url = source.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            unique.append(source)
        return unique


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
