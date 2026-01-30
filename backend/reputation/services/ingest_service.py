from __future__ import annotations

from datetime import datetime, timezone, timedelta
import os
from typing import Iterable, cast

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
        cfg = _as_dict(load_business_config())
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
            cache_note = "; ".join(notes) if notes else "cache hit"
            return ReputationCacheDocument(
                generated_at=datetime.now(timezone.utc),
                config_hash=cfg_hash,
                sources_enabled=sources_enabled,
                items=existing.items,
                stats=ReputationCacheStats(count=len(existing.items), note=cache_note),
            )

        items = self._collect_items(collectors, notes)
        items = self._normalize_items(items, lookback_days)
        items = self._apply_sentiment(cfg, items)
        merged_items = self._merge_items(existing.items if existing else [], items)
        note: str | None = "; ".join(notes) if notes else None

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

    def _apply_sentiment(self, cfg: dict[str, object], items: list[ReputationItem]) -> list[ReputationItem]:
        keywords = self._load_keywords(cfg)
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
        cfg: dict[str, object],
        sources_enabled: list[str],
    ) -> tuple[list[ReputationCollector], list[str]]:
        collectors: list[ReputationCollector] = []
        notes: list[str] = []
        handled_sources: set[str] = set()
        keywords = self._load_keywords(cfg)
        entity_terms = self._load_entity_terms(cfg, keywords)

        if "appstore" in sources_enabled:
            handled_sources.add("appstore")
            appstore_cfg = _as_dict(cfg.get("appstore"))
            if not _get_bool(appstore_cfg, "enabled", False):
                notes.append("appstore: disabled in config.json")
            else:
                app_id_env = _get_str(appstore_cfg, "app_id_env", "APPSTORE_APP_ID")
                country_env = _get_str(appstore_cfg, "country_env", "APPSTORE_COUNTRY")
                max_reviews_env = _get_str(appstore_cfg, "max_reviews_env", "APPSTORE_MAX_REVIEWS")

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
            reddit_cfg = _as_dict(cfg.get("reddit"))
            if not _get_bool(reddit_cfg, "enabled", False):
                notes.append("reddit: disabled in config.json")
            else:
                client_id_env = _get_str(reddit_cfg, "client_id_env", "REDDIT_CLIENT_ID")
                client_secret_env = _get_str(reddit_cfg, "client_secret_env", "REDDIT_CLIENT_SECRET")
                user_agent_env = _get_str(reddit_cfg, "user_agent_env", "REDDIT_USER_AGENT")

                client_id = os.getenv(client_id_env, "").strip()
                client_secret = os.getenv(client_secret_env, "").strip()
                user_agent = os.getenv(user_agent_env, "").strip()

                subreddits = _get_list_str(reddit_cfg, "subreddits")
                query_templates = _get_list_str(reddit_cfg, "query_templates")
                limit_per_query = _get_int(reddit_cfg, "limit_per_query", 100)

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
            twitter_cfg = _as_dict(cfg.get("twitter"))
            if not _get_bool(twitter_cfg, "enabled", False):
                notes.append("twitter: disabled in config.json")
            else:
                bearer_env = _get_str(twitter_cfg, "bearer_token_env", "TWITTER_BEARER_TOKEN")
                max_results_env = _get_str(twitter_cfg, "max_results_env", "TWITTER_MAX_RESULTS")

                bearer = os.getenv(bearer_env, "").strip()
                max_results = _env_int(max_results_env, 100)

                queries = self._default_keyword_queries(keywords)
                if not bearer:
                    notes.append(f"twitter: missing {bearer_env}")
                else:
                    collectors.append(TwitterCollector(bearer, queries, max_results=max_results))

        if "news" in sources_enabled:
            handled_sources.add("news")
            news_cfg = _as_dict(cfg.get("news"))
            if not _get_bool(news_cfg, "enabled", False):
                notes.append("news: disabled in config.json")
            else:
                api_key_env = _get_str(news_cfg, "api_key_env", "NEWS_API_KEY")
                lang_env = _get_str(news_cfg, "lang_env", "NEWS_LANG")
                max_articles_env = _get_str(news_cfg, "max_articles_env", "NEWS_MAX_ARTICLES")
                sources_env = _get_str(news_cfg, "sources_env", "NEWS_SOURCES")
                endpoint_env = _get_str(news_cfg, "endpoint_env", "NEWS_API_ENDPOINT")
                rss_only_env = _get_str(news_cfg, "rss_only_env", "NEWS_RSS_ONLY")
                news_rss_urls = _get_list_str_or_dict(news_cfg, "rss_urls")
                rss_query_env = os.getenv("NEWS_RSS_QUERY_ENABLED", "").strip().lower()
                rss_query_enabled = _get_bool(news_cfg, "rss_query_enabled", True)
                if rss_query_env:
                    rss_query_enabled = rss_query_env in {"1", "true", "yes", "y", "on"}
                rss_geo_map = _get_dict_str_dict_str(news_cfg, "rss_geo_map")

                api_key = os.getenv(api_key_env, "").strip()
                language = os.getenv(lang_env, "es").strip()
                max_articles = _env_int(max_articles_env, 200)
                sources = os.getenv(sources_env, "").strip() or None
                endpoint = os.getenv(endpoint_env, "").strip() or None
                rss_only = _env_bool(os.getenv(rss_only_env, "false"))

                queries = self._default_keyword_queries(entity_terms)
                rss_sources = list(news_rss_urls)
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
            forums_cfg = _as_dict(cfg.get("forums"))
            if not _get_bool(forums_cfg, "enabled", False):
                notes.append("forums: disabled in config.json")
            else:
                scraping_env = _get_str(forums_cfg, "scraping_env", "FORUMS_SCRAPING")
                max_threads_env = _get_str(forums_cfg, "max_threads_env", "FORUMS_MAX_THREADS")
                forum_rss_urls = _get_list_str(forums_cfg, "rss_urls")

                scraping_enabled = _env_bool(os.getenv(scraping_env, "false"))
                max_items = _env_int(max_threads_env, 200)

                if not forum_rss_urls:
                    notes.append("forums: missing rss_urls in config.json")
                else:
                    collectors.append(
                        ForumsCollector(
                            rss_urls=forum_rss_urls,
                            keywords=entity_terms,
                            scraping_enabled=scraping_enabled,
                            max_items=max_items,
                        )
                    )

        if "blogs" in sources_enabled:
            handled_sources.add("blogs")
            blogs_cfg = _as_dict(cfg.get("blogs"))
            if not _get_bool(blogs_cfg, "enabled", False):
                notes.append("blogs: disabled in config.json")
            else:
                rss_only_env = _get_str(blogs_cfg, "rss_only_env", "BLOGS_RSS_ONLY")
                max_items_env = _get_str(blogs_cfg, "max_items_env", "BLOGS_MAX_ITEMS")
                blog_rss_urls = _get_list_str(blogs_cfg, "rss_urls")

                rss_only = _env_bool(os.getenv(rss_only_env, "true"))
                max_items = _env_int(max_items_env, 200)

                if not rss_only:
                    notes.append("blogs: rss_only=false not supported")
                elif not blog_rss_urls:
                    notes.append("blogs: missing rss_urls in config.json")
                else:
                    collectors.append(
                        BlogsCollector(
                            rss_urls=blog_rss_urls,
                            keywords=entity_terms,
                            max_items=max_items,
                        )
                    )

        if "trustpilot" in sources_enabled:
            handled_sources.add("trustpilot")
            trust_cfg = _as_dict(cfg.get("trustpilot"))
            if not _get_bool(trust_cfg, "enabled", False):
                notes.append("trustpilot: disabled in config.json")
            else:
                scraping_env = _get_str(trust_cfg, "scraping_env", "TRUSTPILOT_SCRAPING")
                max_items_env = _get_str(trust_cfg, "max_items_env", "TRUSTPILOT_MAX_ITEMS")
                trust_rss_urls = _get_list_str(trust_cfg, "rss_urls")

                scraping_enabled = _env_bool(os.getenv(scraping_env, "false"))
                max_items = _env_int(max_items_env, 200)

                if not trust_rss_urls:
                    notes.append("trustpilot: missing rss_urls in config.json")
                else:
                    collectors.append(
                        TrustpilotCollector(
                            rss_urls=trust_rss_urls,
                            keywords=entity_terms,
                            scraping_enabled=scraping_enabled,
                            max_items=max_items,
                        )
                    )

        if "google_reviews" in sources_enabled:
            handled_sources.add("google_reviews")
            google_cfg = _as_dict(cfg.get("google_reviews"))
            if not _get_bool(google_cfg, "enabled", False):
                notes.append("google_reviews: disabled in config.json")
            else:
                api_key_env = _get_str(google_cfg, "api_key_env", "GOOGLE_PLACES_API_KEY")
                place_id_env = _get_str(google_cfg, "place_id_env", "GOOGLE_PLACE_ID")
                max_reviews_env = _get_str(google_cfg, "max_reviews_env", "GOOGLE_MAX_REVIEWS")

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
            youtube_cfg = _as_dict(cfg.get("youtube"))
            if not _get_bool(youtube_cfg, "enabled", False):
                notes.append("youtube: disabled in config.json")
            else:
                api_key_env = _get_str(youtube_cfg, "api_key_env", "YOUTUBE_API_KEY")
                max_results_env = _get_str(youtube_cfg, "max_results_env", "YOUTUBE_MAX_RESULTS")

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
            down_cfg = _as_dict(cfg.get("downdetector"))
            if not _get_bool(down_cfg, "enabled", False):
                notes.append("downdetector: disabled in config.json")
            else:
                scraping_env = _get_str(down_cfg, "scraping_env", "DOWNDETECTOR_SCRAPING")
                max_items_env = _get_str(down_cfg, "max_items_env", "DOWNDETECTOR_MAX_ITEMS")
                down_rss_urls = _get_list_str(down_cfg, "rss_urls")

                scraping_enabled = _env_bool(os.getenv(scraping_env, "false"))
                max_items = _env_int(max_items_env, 200)

                if not down_rss_urls:
                    notes.append("downdetector: missing rss_urls in config.json")
                else:
                    collectors.append(
                        DowndetectorCollector(
                            rss_urls=down_rss_urls,
                            keywords=entity_terms,
                            scraping_enabled=scraping_enabled,
                            max_items=max_items,
                        )
                    )

        for source in sources_enabled:
            if source not in handled_sources:
                notes.append(f"{source}: collector not implemented")

        return collectors, notes

    def _auto_enable_rss_sources(self, cfg: dict[str, object], sources_enabled: list[str]) -> list[str]:
        notes: list[str] = []
        rss_sources = ["news", "forums", "blogs", "trustpilot", "downdetector"]

        for source in rss_sources:
            if source in sources_enabled:
                continue
            src_cfg = _as_dict(cfg.get(source))
            if not _get_bool(src_cfg, "enabled", False):
                continue
            rss_urls = _get_list_str_or_dict(src_cfg, "rss_urls")
            if not rss_urls:
                continue

            if source == "news":
                rss_only_env = _get_str(src_cfg, "rss_only_env", "NEWS_RSS_ONLY")
                if not _env_bool(os.getenv(rss_only_env, "false")):
                    continue
            elif source == "blogs":
                rss_only_env = _get_str(src_cfg, "rss_only_env", "BLOGS_RSS_ONLY")
                if not _env_bool(os.getenv(rss_only_env, "true")):
                    continue
            else:
                scraping_env = _get_str(src_cfg, "scraping_env", f"{source.upper()}_SCRAPING")
                if not _env_bool(os.getenv(scraping_env, "false")):
                    continue

            sources_enabled.append(source)
            notes.append(f"{source}: auto-enabled (rss)")

        return notes

    @staticmethod
    def _load_keywords(cfg: dict[str, object]) -> list[str]:
        env_keywords = os.getenv("REPUTATION_KEYWORDS", "").strip()
        if env_keywords:
            return [k.strip() for k in env_keywords.split(",") if k.strip()]
        return _get_list_str(cfg, "keywords")

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
    def _load_entity_terms(cfg: dict[str, object], keywords: list[str]) -> list[str]:
        terms = list(keywords)
        global_competitors = _get_list_str(cfg, "global_competitors")
        competitors_by_geo = _get_dict_str_list_str(cfg, "competidores_por_geografia")
        for name in global_competitors:
            terms.append(name.strip())
        for _, names in competitors_by_geo.items():
            for name in names:
                terms.append(name.strip())
        # Garantiza BBVA como término base
        terms.append("BBVA")
        return list(dict.fromkeys([t for t in terms if t]))

    def _build_news_rss_queries(
        self,
        cfg: dict[str, object],
        geo_map: dict[str, dict[str, str]],
    ) -> list[dict[str, str]]:
        news_cfg = _as_dict(cfg.get("news"))
        templates = _get_list_str(news_cfg, "rss_query_templates")
        if not templates:
            return []

        competitors_by_geo = _get_dict_str_list_str(cfg, "competidores_por_geografia")
        global_competitors = _get_list_str(cfg, "global_competitors")
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
            names = list(competitors)
            names.extend(global_competitors)
            names.extend(bbva_terms)
            for name in names:
                if not name.strip():
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
            url = source.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            unique.append(source)
        return unique


def _as_dict(value: object | None) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _get_bool(cfg: dict[str, object], key: str, default: bool) -> bool:
    value = cfg.get(key)
    return value if isinstance(value, bool) else default


def _get_str(cfg: dict[str, object], key: str, default: str) -> str:
    value = cfg.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return default


def _get_int(cfg: dict[str, object], key: str, default: int) -> int:
    value = cfg.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


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


def _get_dict_str_list_str(cfg: dict[str, object], key: str) -> dict[str, list[str]]:
    value = cfg.get(key)
    if not isinstance(value, dict):
        return {}
    value_dict = cast(dict[str, object], value)
    result: dict[str, list[str]] = {}
    for k, v in value_dict.items():
        if isinstance(v, list):
            items = cast(list[object], v)
            values = [item.strip() for item in items if isinstance(item, str) and item.strip()]
        else:
            values = []
        if values:
            result[k] = values
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
