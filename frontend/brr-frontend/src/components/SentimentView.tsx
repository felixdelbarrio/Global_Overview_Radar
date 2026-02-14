"use client";

/**
 * Vista de sentimiento historico por pais / periodo / fuente.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import dynamic from "next/dynamic";
import {
  AlertTriangle,
  ArrowUpRight,
  Building2,
  Calendar,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clock,
  Loader2,
  MapPin,
  MessageSquare,
  Newspaper,
  User,
  Star,
  PenSquare,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Minus,
  Triangle,
  X,
} from "lucide-react";
import { Shell } from "@/components/Shell";
import { apiGet, apiGetCached, apiPost } from "@/lib/api";
import {
  dispatchIngestStarted,
  INGEST_SUCCESS_EVENT,
  PROFILE_CHANGED_EVENT,
  SETTINGS_CHANGED_EVENT,
  type IngestSuccessDetail,
} from "@/lib/events";
import {
  filterSourcesByScope,
  PRESS_REPUTATION_SOURCE_SET,
} from "@/lib/reputationSources";
import type {
  ActorPrincipalMeta,
  MarketInsightsResponse,
  MarketRating,
  IngestJob,
  ReputationCacheDocument,
  ReputationItem,
  ReputationMeta,
  ResponseSummaryTotals,
} from "@/lib/types";

const SENTIMENTS = ["all", "positive", "neutral", "negative"] as const;
const DISABLED_SCOPE_SOURCE_SENTINEL = "__none__";
const MANUAL_OVERRIDE_BLOCKED_SOURCES = new Set([
  "appstore",
  "googleplay",
  "googlereviews",
]);
const MANUAL_OVERRIDE_BLOCKED_LABELS: Record<string, string> = {
  appstore: "App Store",
  googleplay: "Google Play",
  googlereviews: "Google Reviews",
};
const MARKET_OPINION_SOURCE_KEYS = new Set([
  "appstore",
  "googleplay",
  "googlereviews",
]);
const MARKET_REPLY_TRACKED_SOURCE_KEYS = new Set(["appstore", "googleplay"]);
const MARKET_ACTOR_SOURCE_ORDER = ["appstore", "google_play"] as const;
const MARKET_ACTOR_SOURCE_LABELS: Record<MarketActorSourceKey, string> = {
  appstore: "App Store",
  google_play: "Google Play",
};
const MARKET_ACTOR_SOURCE_COLOR_CLASS: Record<MarketActorSourceKey, string> = {
  appstore: "bg-[#2EA0FF]",
  google_play: "bg-[#46D694]",
};
const PRESS_SOURCE_LABELS: Record<string, string> = {
  news: "News",
  newsapi: "NewsAPI",
  guardian: "The Guardian",
  gdelt: "GDELT",
  downdetector: "Downdetector",
  blogs: "Blogs",
  forums: "Foros",
  trustpilot: "Trustpilot",
  google_reviews: "Google Reviews",
  youtube: "YouTube",
  reddit: "Reddit",
  twitter: "X/Twitter",
};
const PRESS_SOURCE_COLOR_BY_LABEL: Record<string, string> = {
  news: "#1D4ED8",
  newsapi: "#EA580C",
  "the guardian": "#16A34A",
  gdelt: "#DC2626",
  downdetector: "#7C3AED",
  blogs: "#0F766E",
  foros: "#B45309",
  trustpilot: "#059669",
  "google reviews": "#A16207",
  youtube: "#E11D48",
  reddit: "#F97316",
  "x twitter": "#0EA5E9",
  desconocida: "#64748B",
};
const PRESS_SOURCE_COLOR_FALLBACK = [
  "#2563EB",
  "#10B981",
  "#F59E0B",
  "#EF4444",
  "#8B5CF6",
  "#14B8A6",
  "#F97316",
  "#84CC16",
  "#EC4899",
  "#06B6D4",
];

type SentimentFilter = (typeof SENTIMENTS)[number];
type SentimentValue = Exclude<SentimentFilter, "all">;
type MarketActorSourceKey = (typeof MARKET_ACTOR_SOURCE_ORDER)[number];
type MarketActorSourceCounts = Record<MarketActorSourceKey, number>;
type MarketActorRow = {
  key: string;
  label: string;
  count: number;
  sourceCounts: MarketActorSourceCounts;
};
type PressPublisherRow = {
  key: string;
  label: string;
  count: number;
  sourceCounts: Record<string, number>;
};
type OverridePayload = {
  ids: string[];
  geo?: string;
  sentiment?: SentimentValue;
  note?: string;
};
type ReputationCompareGroup = {
  id: string;
  filter: Record<string, unknown>;
  items: ReputationItem[];
  stats: { count: number };
};
type ReputationCompareResponse = {
  groups: ReputationCompareGroup[];
  combined: { items: ReputationItem[]; stats: { count: number } };
};

type DashboardMode = "dashboard" | "sentiment";
type SentimentScope = "all" | "markets" | "press";
type DashboardHeatSource = {
  source: string;
  total: number;
  negative: number;
  negative_ratio: number;
};

type SentimentViewProps = {
  mode?: DashboardMode;
  scope?: SentimentScope;
};

const SentimentChart = dynamic(
  () => import("@/components/SentimentCharts").then((mod) => mod.SentimentChart),
  { ssr: false }
);
const DashboardChart = dynamic(
  () => import("@/components/SentimentCharts").then((mod) => mod.DashboardChart),
  { ssr: false }
);

export function SentimentView({ mode = "sentiment", scope = "all" }: SentimentViewProps) {
  const today = useMemo(() => new Date(), []);
  const defaultTo = useMemo(() => toDateInput(today), [today]);
  const defaultFrom = useMemo(() => toDateInput(startOfMonth(today)), [today]);
  const todayInput = useMemo(() => toDateInput(today), [today]);
  const currentDashboardMonth = useMemo(() => startOfMonth(today), [today]);
  const [dashboardMonthCursor, setDashboardMonthCursor] = useState(() => startOfMonth(today));
  const dashboardFrom = useMemo(
    () => toDateInput(startOfMonth(dashboardMonthCursor)),
    [dashboardMonthCursor],
  );
  const dashboardTo = useMemo(() => {
    if (isSameMonth(dashboardMonthCursor, today)) return todayInput;
    return toDateInput(endOfMonth(dashboardMonthCursor));
  }, [dashboardMonthCursor, today, todayInput]);

  const [items, setItems] = useState<ReputationItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(true);
  const [chartItems, setChartItems] = useState<ReputationItem[]>([]);
  const [chartLoading, setChartLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);
  const [actorPrincipal, setActorPrincipal] = useState<ActorPrincipalMeta | null>(null);
  const [meta, setMeta] = useState<ReputationMeta | null>(null);
  const [marketRatings, setMarketRatings] = useState<MarketRating[]>([]);
  const [marketRatingsHistory, setMarketRatingsHistory] = useState<MarketRating[]>([]);
  const [dashboardMarketInsights, setDashboardMarketInsights] =
    useState<MarketInsightsResponse | null>(null);
  const [dashboardMarketInsightsLoading, setDashboardMarketInsightsLoading] =
    useState(false);
  const [dashboardMarketInsightsError, setDashboardMarketInsightsError] =
    useState<string | null>(null);

  const [fromDate, setFromDate] = useState(defaultFrom);
  const [toDate, setToDate] = useState(defaultTo);
  const [sentiment, setSentiment] = useState<SentimentFilter>("all");
  const [geo, setGeo] = useState("all");
  const [actor, setActor] = useState("all");
  const [actorMemory, setActorMemory] = useState<Record<string, string>>({});
  const [filterMemory, setFilterMemory] = useState<
    Record<string, { sentiment: SentimentFilter; sources: string[] }>
  >({});
  const [filterRestoredAt, setFilterRestoredAt] = useState<number | null>(null);
  const lastGeoRef = useRef<string | null>(null);
  const sentimentRef = useRef<SentimentFilter>(sentiment);
  const sourcesRef = useRef<string[]>([]);
  const ingestRefreshTimersRef = useRef<number[]>([]);
  const chartSectionRef = useRef<HTMLDivElement | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [overrideRefresh, setOverrideRefresh] = useState(0);
  const [reputationRefresh, setReputationRefresh] = useState(0);
  const [profileRefresh, setProfileRefresh] = useState(0);
  const [chartsVisible, setChartsVisible] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [reputationIngesting, setReputationIngesting] = useState(false);
  const [reputationIngestNote, setReputationIngestNote] = useState<string | null>(null);
  const [cacheNoticeDismissed, setCacheNoticeDismissed] = useState(false);
  const defaultGeoAppliedRef = useRef(false);
  const isDashboard = mode === "dashboard";
  const isSentimentMarkets = !isDashboard && scope === "markets";
  const isSentimentPress = !isDashboard && scope === "press";
  const effectiveSentiment = isDashboard ? "all" : sentiment;
  const effectiveActor = isDashboard ? "all" : actor;
  const comparisonsEnabled = !isDashboard && Boolean(meta?.ui_show_comparisons);
  const actorForSeries = comparisonsEnabled ? effectiveActor : "all";
  const effectiveFromDate = isDashboard ? dashboardFrom : fromDate;
  const effectiveToDate = isDashboard ? dashboardTo : toDate;
  const entityParam = useMemo(
    () =>
      isDashboard
        ? "actor_principal"
        : effectiveActor === "all"
          ? "all"
          : "actor_principal",
    [isDashboard, effectiveActor],
  );
  const showDownloads = mode === "sentiment";
  // Defensive: sometimes `meta.cache_available` may lag behind the actual items state
  // (eg. when the cache is generated while the page is loading). Avoid showing the
  // "Sin cache" banner if we already have items to display.
  const reputationCacheMissing =
    meta?.cache_available === false && !itemsLoading && items.length === 0;
  const showCacheNotice = reputationCacheMissing && !cacheNoticeDismissed;

  const touchItemsFilters = () => {
    setError(null);
  };

  const touchChartFilters = () => {
    setChartError(null);
    setChartLoading(true);
  };

  const touchCommonFilters = () => {
    touchItemsFilters();
    touchChartFilters();
  };

  const canGoDashboardNext = useMemo(
    () => dashboardMonthCursor.getTime() < currentDashboardMonth.getTime(),
    [dashboardMonthCursor, currentDashboardMonth],
  );
  const dashboardMonthLabel = useMemo(
    () => formatMonthLabel(dashboardMonthCursor),
    [dashboardMonthCursor],
  );
  const handleDashboardPrevMonth = () => {
    touchCommonFilters();
    setDashboardMonthCursor((value) => shiftMonth(value, -1));
  };
  const handleDashboardNextMonth = () => {
    touchCommonFilters();
    setDashboardMonthCursor((value) => {
      const next = shiftMonth(value, 1);
      if (next.getTime() > currentDashboardMonth.getTime()) {
        return currentDashboardMonth;
      }
      return next;
    });
  };

  useEffect(() => {
    if (!isDashboard) return;
    if (sentiment !== "all") setSentiment("all");
    if (actor !== "all") setActor("all");
  }, [isDashboard, sentiment, actor]);

  useEffect(() => {
    if (comparisonsEnabled) return;
    if (actor !== "all") {
      setActor("all");
    }
  }, [comparisonsEnabled, actor]);

  useEffect(() => {
    if (chartsVisible) return;
    const node = chartSectionRef.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setChartsVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setChartsVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [chartsVisible]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const scheduleRefresh = (delayMs: number) => {
      const timer = window.setTimeout(() => {
        setReputationRefresh((value) => value + 1);
        ingestRefreshTimersRef.current = ingestRefreshTimersRef.current.filter(
          (value) => value !== timer,
        );
      }, delayMs);
      ingestRefreshTimersRef.current.push(timer);
    };
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<IngestSuccessDetail>).detail;
      if (!detail || detail.kind !== "reputation") return;
      setReputationRefresh((value) => value + 1);
      // Cloud Run/GCS can expose the finished job a little before all reads converge.
      scheduleRefresh(1500);
      scheduleRefresh(4500);
    };
    window.addEventListener(INGEST_SUCCESS_EVENT, handler as EventListener);
    return () => {
      window.removeEventListener(INGEST_SUCCESS_EVENT, handler as EventListener);
      ingestRefreshTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      ingestRefreshTimersRef.current = [];
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const handler = () => {
      setProfileRefresh((value) => value + 1);
      setReputationRefresh((value) => value + 1);
    };
    window.addEventListener(PROFILE_CHANGED_EVENT, handler as EventListener);
    return () => {
      window.removeEventListener(PROFILE_CHANGED_EVENT, handler as EventListener);
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const handler = () => {
      setProfileRefresh((value) => value + 1);
      setReputationRefresh((value) => value + 1);
    };
    window.addEventListener(SETTINGS_CHANGED_EVENT, handler as EventListener);
    return () => {
      window.removeEventListener(SETTINGS_CHANGED_EVENT, handler as EventListener);
    };
  }, []);

  const handleOverride = async (payload: OverridePayload) => {
    await apiPost<{ updated: number }>("/reputation/items/override", payload);
    setOverrideRefresh((value) => value + 1);
  };

  const handleStartReputationIngest = async () => {
    setCacheNoticeDismissed(true);
    setReputationIngestNote(null);
    setReputationIngesting(true);
    try {
      const job = await apiPost<IngestJob>("/ingest/reputation", {
        force: false,
        all_sources: false,
      });
      if (job?.id) {
        dispatchIngestStarted(job);
      }
      setReputationIngestNote(
        "Ingesta iniciada. Puedes seguir el progreso en el centro de ingestas.",
      );
    } catch {
      setReputationIngestNote(
        "No se pudo iniciar la ingesta. Inténtalo de nuevo.",
      );
    } finally {
      setReputationIngesting(false);
    }
  };

  useEffect(() => {
    if (!reputationCacheMissing) {
      setCacheNoticeDismissed(false);
    }
  }, [reputationCacheMissing]);

  useEffect(() => {
    setCacheNoticeDismissed(false);
  }, [profileRefresh, reputationRefresh]);

  const actorPrincipalName = useMemo(
    () => actorPrincipal?.canonical || "Actor principal",
    [actorPrincipal],
  );
  const principalAliases = useMemo(
    () => buildPrincipalAliases(actorPrincipal),
    [actorPrincipal],
  );
  const principalAliasKeys = useMemo(
    () =>
      Array.from(new Set(principalAliases.map(normalizeKey).filter(Boolean))),
    [principalAliases],
  );
  const scopeAllowedSources = useMemo(() => {
    const fromMeta = (meta?.sources_enabled ?? meta?.sources_available ?? []).filter(Boolean);
    if (isDashboard) return fromMeta;
    return filterSourcesByScope(fromMeta, scope);
  }, [meta, isDashboard, scope]);
  const effectiveSourcesForQuery = useMemo(() => {
    if (sources.length) return sources;
    if (isDashboard) return [];
    if (scopeAllowedSources.length) return scopeAllowedSources;
    return [DISABLED_SCOPE_SOURCE_SENTINEL];
  }, [sources, isDashboard, scopeAllowedSources]);
  const showResponsesSummary = isSentimentMarkets || isDashboard;
  const listedSentimentLabel = useMemo(
    () => formatSentimentFilterLabel(effectiveSentiment),
    [effectiveSentiment],
  );
  const listedGeoLabel = geo === "all" ? "Todos" : geo;
  const listedFiltersLabel = useMemo(
    () =>
      [
        `${formatDateInputLabel(effectiveFromDate)} - ${formatDateInputLabel(effectiveToDate)}`,
        `SENTIMIENTO: ${listedSentimentLabel}`,
        `PAÍS: ${listedGeoLabel}`,
      ].join(" · "),
    [effectiveFromDate, effectiveToDate, listedSentimentLabel, listedGeoLabel],
  );

  useEffect(() => {
    let alive = true;
    apiGetCached<ReputationMeta>("/reputation/meta", {
      ttlMs: 60000,
      force: profileRefresh > 0 || reputationRefresh > 0,
    })
      .then((meta) => {
        if (!alive) return;
        setActorPrincipal(meta.actor_principal ?? null);
        setMeta(meta);
        setMarketRatings(meta.market_ratings ?? []);
        setMarketRatingsHistory(meta.market_ratings_history ?? []);
      })
      .catch(() => {
        if (alive) {
          setActorPrincipal(null);
          setMeta(null);
          setMarketRatings([]);
        }
      });
    return () => {
      alive = false;
    };
  }, [profileRefresh, reputationRefresh]);

  useEffect(() => {
    let alive = true;

    // If comparing actor principal vs another actor, request both datasets and combine them.
    const fetchCombinedIfComparing = async () => {
      setItemsLoading(true);
      if (
        comparisonsEnabled &&
        effectiveActor !== "all" &&
        !isPrincipalName(effectiveActor, principalAliasKeys)
      ) {
        const makeFilter = (overrides: Partial<Record<string, unknown>>) => {
          const f: Record<string, unknown> = {};
          if (effectiveFromDate) f.from_date = effectiveFromDate;
          if (effectiveToDate) f.to_date = effectiveToDate;
          if (effectiveSentiment !== "all") f.sentiment = effectiveSentiment;
          if (geo !== "all") f.geo = geo;
          if (effectiveSourcesForQuery.length) {
            f.sources = effectiveSourcesForQuery.join(",");
          }
          return { ...f, ...overrides };
        };

        const payload = [
          makeFilter({ entity: "actor_principal" }),
          makeFilter({ actor: effectiveActor }),
        ];

        try {
          const doc = await apiPost<ReputationCompareResponse>(
            "/reputation/items/compare",
            payload,
          );
          if (!alive) return;
          setItems(doc.combined.items ?? []);
          setError(null);
        } catch (e) {
          if (alive) setError(String(e));
        } finally {
          if (alive) setItemsLoading(false);
        }
        return;
      }

      const params = new URLSearchParams();
      if (effectiveFromDate) params.set("from_date", effectiveFromDate);
      if (effectiveToDate) params.set("to_date", effectiveToDate);
      if (effectiveSentiment !== "all") params.set("sentiment", effectiveSentiment);
      params.set("entity", entityParam);
      if (geo !== "all") params.set("geo", geo);
      // When actor is specific, compare flow handles filters. Otherwise use entityParam.
      if (effectiveSourcesForQuery.length) {
        params.set("sources", effectiveSourcesForQuery.join(","));
      }

      try {
        const doc = await apiGet<ReputationCacheDocument>(`/reputation/items?${params.toString()}`);
        if (!alive) return;
        setItems(doc.items ?? []);
        setLastUpdatedAt(doc.generated_at ?? null);
        setError(null);
      } catch (e) {
        if (alive) setError(String(e));
      } finally {
        if (alive) setItemsLoading(false);
      }
    };

    void fetchCombinedIfComparing();

    return () => {
      alive = false;
    };
  }, [
    effectiveFromDate,
    effectiveToDate,
    effectiveSentiment,
    comparisonsEnabled,
    entityParam,
    geo,
    effectiveActor,
    effectiveSourcesForQuery,
    principalAliasKeys,
    overrideRefresh,
    reputationRefresh,
  ]);

  useEffect(() => {
    let alive = true;
    const params = new URLSearchParams();
    if (effectiveFromDate) params.set("from_date", effectiveFromDate);
    if (effectiveToDate) params.set("to_date", effectiveToDate);
    if (effectiveSentiment !== "all") params.set("sentiment", effectiveSentiment);
    if (geo !== "all") params.set("geo", geo);
    if (effectiveSourcesForQuery.length) {
      params.set("sources", effectiveSourcesForQuery.join(","));
    }

    apiGet<ReputationCacheDocument>(`/reputation/items?${params.toString()}`)
      .then((doc) => {
        if (!alive) return;
        setChartItems(doc.items ?? []);
        setLastUpdatedAt(doc.generated_at ?? null);
        setChartError(null);
      })
      .catch((e) => {
        if (alive) setChartError(String(e));
      })
      .finally(() => {
        if (alive) setChartLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [
    effectiveFromDate,
    effectiveToDate,
    effectiveSentiment,
    geo,
    effectiveSourcesForQuery,
    overrideRefresh,
    reputationRefresh,
  ]);

  useEffect(() => {
    let alive = true;
    if (!isDashboard) {
      setDashboardMarketInsights(null);
      setDashboardMarketInsightsLoading(false);
      setDashboardMarketInsightsError(null);
      return () => {
        alive = false;
      };
    }

    setDashboardMarketInsightsLoading(true);
    setDashboardMarketInsightsError(null);

    const params = new URLSearchParams();
    if (effectiveFromDate) params.set("from_date", effectiveFromDate);
    if (effectiveToDate) params.set("to_date", effectiveToDate);
    if (geo !== "all") params.set("geo", geo);
    const validSources = effectiveSourcesForQuery.filter(
      (source) => source && source !== DISABLED_SCOPE_SOURCE_SENTINEL,
    );
    if (validSources.length) {
      params.set("sources", validSources.join(","));
    }

    apiGet<MarketInsightsResponse>(`/reputation/markets/insights?${params.toString()}`)
      .then((doc) => {
        if (!alive) return;
        setDashboardMarketInsights(doc);
      })
      .catch((e) => {
        if (!alive) return;
        setDashboardMarketInsights(null);
        setDashboardMarketInsightsError(String(e));
      })
      .finally(() => {
        if (alive) {
          setDashboardMarketInsightsLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, [
    isDashboard,
    effectiveFromDate,
    effectiveToDate,
    geo,
    effectiveSourcesForQuery,
    profileRefresh,
    reputationRefresh,
  ]);

  const sourceCounts = useMemo(() => {
    const counts: Record<string, { principal: number; others: number; total: number }> = {};
    for (const item of items) {
      if (!item.source) continue;
      const bucket = counts[item.source] ?? { principal: 0, others: 0, total: 0 };
      bucket.total += 1;
      if (isPrincipalItem(item, principalAliasKeys)) {
        bucket.principal += 1;
      } else {
        bucket.others += 1;
      }
      counts[item.source] = bucket;
    }
    return counts;
  }, [items, principalAliasKeys]);
  const sourcesOptions = useMemo(() => {
    const fromCounts = Object.keys(sourceCounts);
    if (fromCounts.length) {
      return filterSourcesByScope(fromCounts, isDashboard ? "all" : scope).sort((a, b) =>
        a.localeCompare(b),
      );
    }
    const fromMeta = meta?.sources_available ?? meta?.sources_enabled ?? [];
    return filterSourcesByScope(fromMeta.filter(Boolean), isDashboard ? "all" : scope).sort(
      (a, b) => a.localeCompare(b),
    );
  }, [sourceCounts, meta, isDashboard, scope]);
  const sortedSources = useMemo(() => [...sources].sort(), [sources]);
  useEffect(() => {
    sentimentRef.current = sentiment;
  }, [sentiment]);
  useEffect(() => {
    sourcesRef.current = sortedSources;
  }, [sortedSources]);
  useEffect(() => {
    if (!sources.length) return;
    const allowed = new Set(sourcesOptions);
    const next = sources.filter((source) => allowed.has(source));
    if (next.length !== sources.length) {
      setSources(next);
    }
  }, [sourcesOptions, sources]);
  const geoOptions = useMemo(() => {
    const fromMeta = meta?.geos ?? [];
    const fromItems = items.map((i) => i.geo).filter(Boolean) as string[];
    return unique([...fromMeta, ...fromItems]).sort((a, b) => a.localeCompare(b));
  }, [items, meta]);
  const preferredGeo = useMemo(
    () => findDefaultGeoOption(geoOptions),
    [geoOptions],
  );

  useEffect(() => {
    if (defaultGeoAppliedRef.current) return;
    if (!geoOptions.length) return;
    defaultGeoAppliedRef.current = true;
    if (geo === "all" && preferredGeo) {
      setGeo(preferredGeo);
    }
  }, [geoOptions, preferredGeo, geo]);

  const availableActorSet = useMemo(() => {
    const values = chartItems
      .map((i) => i.actor)
      .filter(Boolean) as string[];
    return new Set(values.map((value) => normalizeKey(value)));
  }, [chartItems]);

  const allowedActorSet = useMemo(() => {
    if (geo === "all") return null;
    const fromMetaGeo = (meta?.otros_actores_por_geografia ?? {})[geo] ?? [];
    const fromMetaGlobal = meta?.otros_actores_globales ?? [];
    return new Set(
      [...fromMetaGeo, ...fromMetaGlobal].map((value) => normalizeKey(value)),
    );
  }, [geo, meta]);

  const actorOptions = useMemo(() => {
    const fromMetaGeo = (meta?.otros_actores_por_geografia ?? {})[geo] ?? [];
    const fromMetaGlobal = meta?.otros_actores_globales ?? [];
    const fromItems = chartItems.map((i) => i.actor).filter(Boolean) as string[];
    const base =
      geo !== "all"
        ? [...fromMetaGeo, ...fromMetaGlobal]
        : fromItems;
    const values = unique(base).filter(Boolean);
    return values
      .filter((v) => !isPrincipalName(v, principalAliasKeys))
      .filter((v) => (allowedActorSet ? allowedActorSet.has(normalizeKey(v)) : true))
      .filter((v) => availableActorSet.has(normalizeKey(v)))
      .sort((a, b) => a.localeCompare(b));
  }, [chartItems, principalAliasKeys, geo, meta, availableActorSet, allowedActorSet]);

  useEffect(() => {
    if (isDashboard || actor === "all") return;
    setActorMemory((current) => ({ ...current, [geo]: actor }));
  }, [actor, geo, isDashboard]);

  useEffect(() => {
    setFilterMemory((current) => ({
      ...current,
      [geo]: { sentiment: isDashboard ? "all" : sentiment, sources: sortedSources },
    }));
  }, [sentiment, sortedSources, geo, isDashboard]);

  useEffect(() => {
    if (isDashboard) return;
    const normalized = normalizeKey(actor);
    const stored = actorMemory[geo];
    if (actor === "all") {
      return;
    }
    if (actor !== "all" && availableActorSet.has(normalized)) {
      return;
    }
    if (stored && availableActorSet.has(normalizeKey(stored))) {
      setActor(stored);
      return;
    }
    if (actor !== "all") {
      setActor("all");
    }
  }, [geo, actor, actorMemory, availableActorSet, isDashboard]);

  useEffect(() => {
    if (lastGeoRef.current === geo) return;
    lastGeoRef.current = geo;
    const stored = filterMemory[geo];
    if (!stored) return;
    let changed = false;
    if (!isDashboard) {
      const currentSentiment = sentimentRef.current;
      if (stored.sentiment !== currentSentiment) {
        setSentiment(stored.sentiment);
        changed = true;
      }
    }
    const storedSources = stored.sources || [];
    const currentSources = sourcesRef.current || [];
    const sameSources =
      storedSources.length === currentSources.length &&
      storedSources.every((value) => currentSources.includes(value));
    if (!sameSources) {
      setSources(storedSources);
      changed = true;
    }
    if (changed) {
      setFilterRestoredAt(Date.now());
    }
  }, [geo, filterMemory, isDashboard]);

  useEffect(() => {
    if (!filterRestoredAt) return;
    const timer = window.setTimeout(() => {
      setFilterRestoredAt(null);
    }, 3500);
    return () => window.clearTimeout(timer);
  }, [filterRestoredAt]);

  const sentimentSummary = useMemo(() => summarize(items), [items]);
  const principalItems = useMemo(
    () => items.filter((item) => isPrincipalItem(item, principalAliasKeys)),
    [items, principalAliasKeys],
  );
  const otherItems = useMemo(
    () => items.filter((item) => !isPrincipalItem(item, principalAliasKeys)),
    [items, principalAliasKeys],
  );
  const principalSentimentSummary = useMemo(() => summarize(principalItems), [principalItems]);
  const otherSentimentSummary = useMemo(() => summarize(otherItems), [otherItems]);
  const splitSummaryByActor = !isDashboard && comparisonsEnabled;
  const mentionsSummaryPrincipal = useMemo(
    () =>
      (isDashboard ? items.length : principalItems.length).toLocaleString("es-ES"),
    [isDashboard, items.length, principalItems.length],
  );
  const mentionsSummaryComparison = useMemo(
    () => (splitSummaryByActor ? otherItems.length.toLocaleString("es-ES") : null),
    [splitSummaryByActor, otherItems.length],
  );
  const scoreSummaryPrincipal = useMemo(
    () =>
      (isDashboard ? sentimentSummary.avgScore : principalSentimentSummary.avgScore).toFixed(2),
    [isDashboard, sentimentSummary.avgScore, principalSentimentSummary.avgScore],
  );
  const scoreSummaryComparison = useMemo(
    () => (splitSummaryByActor ? otherSentimentSummary.avgScore.toFixed(2) : null),
    [splitSummaryByActor, otherSentimentSummary.avgScore],
  );
  const positivesSummaryPrincipal = useMemo(
    () =>
      (isDashboard ? sentimentSummary.positive : principalSentimentSummary.positive).toLocaleString(
        "es-ES",
      ),
    [isDashboard, sentimentSummary.positive, principalSentimentSummary.positive],
  );
  const positivesSummaryComparison = useMemo(
    () => (splitSummaryByActor ? otherSentimentSummary.positive.toLocaleString("es-ES") : null),
    [splitSummaryByActor, otherSentimentSummary.positive],
  );
  const neutralsSummaryPrincipal = useMemo(
    () =>
      (isDashboard ? sentimentSummary.neutral : principalSentimentSummary.neutral).toLocaleString(
        "es-ES",
      ),
    [isDashboard, sentimentSummary.neutral, principalSentimentSummary.neutral],
  );
  const negativesSummaryPrincipal = useMemo(
    () =>
      (isDashboard ? sentimentSummary.negative : principalSentimentSummary.negative).toLocaleString(
        "es-ES",
      ),
    [isDashboard, sentimentSummary.negative, principalSentimentSummary.negative],
  );
  const negativesSummaryComparison = useMemo(
    () => (splitSummaryByActor ? otherSentimentSummary.negative.toLocaleString("es-ES") : null),
    [splitSummaryByActor, otherSentimentSummary.negative],
  );
  const sentimentSeries = useMemo(
    () =>
      buildComparativeSeries(
        chartItems,
        actorForSeries,
        principalAliasKeys,
        effectiveFromDate,
        effectiveToDate,
      ),
    [chartItems, actorForSeries, principalAliasKeys, effectiveFromDate, effectiveToDate],
  );
  const dashboardSeries = useMemo(
    () =>
      sentimentSeries.map((row) => ({
        date: row.date,
        sentiment: typeof row.principal === "number" ? row.principal : null,
      })),
    [sentimentSeries],
  );
  const groupedMentions = useMemo(() => groupMentions(items), [items]);
  const rangeLabel = useMemo(
    () => buildRangeLabel(effectiveFromDate, effectiveToDate),
    [effectiveFromDate, effectiveToDate],
  );
  const mentionsPeriodLabel = useMemo(
    () => buildMentionsPeriodLabel(effectiveFromDate, effectiveToDate),
    [effectiveFromDate, effectiveToDate],
  );
  const latestTimestamp = useMemo(
    () => lastUpdatedAt || getLatestDate(items),
    [lastUpdatedAt, items],
  );
  const latestLabel = useMemo(
    () => formatDate(latestTimestamp),
    [latestTimestamp],
  );
  const principalLabel = useMemo(
    () => buildEntityLabel(actorPrincipalName, geo),
    [actorPrincipalName, geo],
  );
  const actorLabel = useMemo(
    () =>
      buildEntityLabel(
        effectiveActor &&
          effectiveActor !== "all" &&
          !isPrincipalName(effectiveActor, principalAliasKeys)
          ? effectiveActor
          : "Otros actores del mercado",
        geo,
      ),
    [effectiveActor, geo, principalAliasKeys],
  );
  const selectedActor = useMemo(
    () =>
      comparisonsEnabled &&
      effectiveActor !== "all" &&
      !isPrincipalName(effectiveActor, principalAliasKeys)
        ? effectiveActor
        : null,
    [comparisonsEnabled, effectiveActor, principalAliasKeys],
  );
  const selectedActorKey = useMemo(
    () => (selectedActor ? normalizeKey(selectedActor) : null),
    [selectedActor],
  );
  const filteredMarketItems = useMemo(
    () =>
      selectedActorKey
        ? items.filter(
            (item) =>
              isPrincipalItem(item, principalAliasKeys) ||
              normalizeKey(item.actor || "") === selectedActorKey,
          )
        : items,
    [items, principalAliasKeys, selectedActorKey],
  );
  const marketActorItems = useMemo(
    () =>
      comparisonsEnabled
        ? filteredMarketItems
        : filteredMarketItems.filter((item) => isPrincipalItem(item, principalAliasKeys)),
    [comparisonsEnabled, filteredMarketItems, principalAliasKeys],
  );
  const marketActorRows = useMemo(
    () => buildMarketActorRows(marketActorItems),
    [marketActorItems],
  );
  const marketSourceTotals = useMemo(
    () => countMarketSourceTotals(marketActorItems),
    [marketActorItems],
  );
  const pressContextItems = useMemo(() => {
    if (isDashboard) return [] as ReputationItem[];
    if (!comparisonsEnabled) {
      return items.filter((item) => isPrincipalItem(item, principalAliasKeys));
    }
    return items;
  }, [isDashboard, comparisonsEnabled, items, principalAliasKeys]);
  const activePressSources = useMemo(() => {
    if (isDashboard) return new Set<string>();
    const selectedOrScopedSources = sources.length
      ? sources
      : scope === "press"
        ? scopeAllowedSources
        : [];
    return new Set(
      selectedOrScopedSources
        .map((source) => normalizeSourceKey(source))
        .filter((sourceKey) => PRESS_REPUTATION_SOURCE_SET.has(sourceKey)),
    );
  }, [isDashboard, sources, scope, scopeAllowedSources]);
  const pressItems = useMemo(
    () =>
      pressContextItems.filter((item) => {
        const sourceKey = normalizeSourceKey(item.source || "");
        if (!PRESS_REPUTATION_SOURCE_SET.has(sourceKey)) return false;
        if (!activePressSources.size) return true;
        return activePressSources.has(sourceKey);
      }),
    [pressContextItems, activePressSources],
  );
  const pressPublisherRows = useMemo(
    () => buildPressPublisherRows(pressItems),
    [pressItems],
  );
  const pressPublisherSourceTotals = useMemo(
    () => countPressPublisherSourceTotals(pressItems),
    [pressItems],
  );
  const showPressPublishersBlock = !isDashboard && !isSentimentMarkets;
  const selectedMarketActorLabel = selectedActor || "Otro actor del mercado";
  const storeSourcesEnabled = useMemo(
    () => new Set((meta?.sources_enabled ?? []).map((src) => src.toLowerCase())),
    [meta?.sources_enabled],
  );
  const appleStoreEnabled = storeSourcesEnabled.has("appstore");
  const googlePlayEnabled = storeSourcesEnabled.has("google_play");
  const showStoreRatings = !isSentimentPress && (appleStoreEnabled || googlePlayEnabled);
  const hasGeoSelection = geo !== "all";
  const showStoreRatingsForGeo = showStoreRatings && hasGeoSelection;
  const principalStoreRatings = useMemo(
    () => buildActorStoreRatings(marketRatings, actorPrincipalName, geo),
    [marketRatings, actorPrincipalName, geo],
  );
  const actorStoreRatings = useMemo(
    () => (selectedActor ? buildActorStoreRatings(marketRatings, selectedActor, geo) : null),
    [marketRatings, selectedActor, geo],
  );
  const storeRatingVisibility = useMemo(
    () => ({
      showApple: appleStoreEnabled,
      showGoogle: googlePlayEnabled,
    }),
    [appleStoreEnabled, googlePlayEnabled],
  );
  const principalMentions = useMemo(
    () => groupedMentions.filter((item) => isPrincipalGroup(item, principalAliasKeys)),
    [groupedMentions, principalAliasKeys],
  );
  const actorMentions = useMemo(
    () =>
      groupedMentions.filter((item) => {
        if (isPrincipalGroup(item, principalAliasKeys)) return false;
        if (!item.actor) return false;
        if (!selectedActorKey) return true;
        return normalizeKey(item.actor || "") === selectedActorKey;
      }),
    [groupedMentions, principalAliasKeys, selectedActorKey],
  );
  const selectedActorMentionsSummary = useMemo(() => {
    const counts = { total: actorMentions.length, positive: 0, neutral: 0, negative: 0 };
    for (const item of actorMentions) {
      if (item.sentiment === "positive") counts.positive += 1;
      if (item.sentiment === "neutral") counts.neutral += 1;
      if (item.sentiment === "negative") counts.negative += 1;
    }
    return counts;
  }, [actorMentions]);
  const selectedActorMentionsTotalLabel = useMemo(
    () => selectedActorMentionsSummary.total.toLocaleString("es-ES"),
    [selectedActorMentionsSummary.total],
  );
  const dashboardTopPenalizedFeatures = useMemo(
    () => (dashboardMarketInsights?.top_penalized_features ?? []).slice(0, 10),
    [dashboardMarketInsights],
  );
  const dashboardAlerts = useMemo(
    () => dashboardMarketInsights?.alerts ?? [],
    [dashboardMarketInsights],
  );
  const dashboardSourceFriction = useMemo(
    () => dashboardMarketInsights?.source_friction ?? [],
    [dashboardMarketInsights],
  );
  const dashboardResponseSourceFriction = useMemo(
    () => dashboardMarketInsights?.response_source_friction ?? [],
    [dashboardMarketInsights],
  );
  const dashboardResponseOpinionsTotal = useMemo(() => {
    const total = Number(dashboardMarketInsights?.responses?.totals?.opinions_total ?? 0);
    if (!Number.isFinite(total) || total <= 0) return 0;
    return total;
  }, [dashboardMarketInsights]);
  const dashboardHeatSources = useMemo<DashboardHeatSource[]>(() => {
    const sourceRows = (dashboardResponseSourceFriction.length
      ? dashboardResponseSourceFriction
      : dashboardSourceFriction
    ).filter((entry) => MARKET_REPLY_TRACKED_SOURCE_KEYS.has(normalizeSourceKey(entry.source)));
    const denominator =
      dashboardResponseOpinionsTotal > 0
        ? dashboardResponseOpinionsTotal
        : sourceRows.reduce((sum, entry) => sum + Math.max(0, Number(entry.total ?? 0)), 0);
    if (!Number.isFinite(denominator) || denominator <= 0) return [];
    return sourceRows
      .map((entry) => {
        const negative = Math.max(0, Number(entry.negative ?? 0));
        return {
          source: entry.source,
          total: denominator,
          negative,
          negative_ratio: negative / denominator,
        };
      })
      .sort((a, b) => {
        if (b.negative_ratio !== a.negative_ratio) return b.negative_ratio - a.negative_ratio;
        if (b.negative !== a.negative) return b.negative - a.negative;
        return a.source.localeCompare(b.source);
      });
  }, [dashboardResponseSourceFriction, dashboardSourceFriction, dashboardResponseOpinionsTotal]);
  const dashboardHeatDenominator = useMemo(() => {
    const fromRows = dashboardHeatSources[0]?.total ?? 0;
    if (Number.isFinite(fromRows) && fromRows > 0) return fromRows;
    if (dashboardResponseOpinionsTotal > 0) return dashboardResponseOpinionsTotal;
    return 0;
  }, [dashboardHeatSources, dashboardResponseOpinionsTotal]);
  const principalReplyTrackedMentions = useMemo(
    () =>
      principalMentions.filter((item) =>
        item.sources.some((source) =>
          MARKET_REPLY_TRACKED_SOURCE_KEYS.has(normalizeSourceKey(source.name)),
        ),
      ),
    [principalMentions],
  );
  const actorReplyTrackedMentions = useMemo(
    () =>
      actorMentions.filter((item) =>
        item.sources.some((source) =>
          MARKET_REPLY_TRACKED_SOURCE_KEYS.has(normalizeSourceKey(source.name)),
        ),
      ),
    [actorMentions],
  );
  const dashboardResponseTotals = useMemo(
    () => toAnsweredMentionTotals(dashboardMarketInsights?.responses?.totals),
    [dashboardMarketInsights],
  );
  const dashboardMaxFeatureCount = useMemo(
    () =>
      Math.max(
        1,
        ...dashboardTopPenalizedFeatures.map((entry) => Number(entry.count || 0)),
      ),
    [dashboardTopPenalizedFeatures],
  );
  const [mentionsTab, setMentionsTab] = useState<"principal" | "actor">("principal");
  const effectiveMentionsTab = comparisonsEnabled ? mentionsTab : "principal";

  const mentionsToShow =
    effectiveMentionsTab === "principal" ? principalMentions : actorMentions;
  const mentionsLabel = effectiveMentionsTab === "principal" ? principalLabel : actorLabel;
  const errorMessage = error || chartError;
  // "Ultimas menciones" depende solo del dataset de items, no del fetch del grafico.
  const mentionsLoading = itemsLoading;
  const splitResponsesByActor = !isDashboard && comparisonsEnabled;
  const responseSummaryUsesRatios = isDashboard || isSentimentMarkets;
  const responseCoverageIncludeTotals = !isDashboard && !isSentimentMarkets;
  const responseTotalsPrincipal = useMemo(() => {
    if (isDashboard) {
      return dashboardResponseTotals ?? summarizeAnsweredMentions(principalReplyTrackedMentions);
    }
    if (isSentimentMarkets) {
      return summarizeAnsweredMentions(principalReplyTrackedMentions);
    }
    return summarizeAnsweredMentions(principalMentions);
  }, [
    isDashboard,
    isSentimentMarkets,
    dashboardResponseTotals,
    principalReplyTrackedMentions,
    principalMentions,
  ]);
  const responseTotalsComparison = splitResponsesByActor
    ? summarizeAnsweredMentions(isSentimentMarkets ? actorReplyTrackedMentions : actorMentions)
    : null;
  const showSecondaryMarketResponses = Boolean(
    isSentimentMarkets && selectedActor && responseTotalsComparison,
  );
  const answeredTotalPrincipalLabel = responseTotalsPrincipal.answeredTotal.toLocaleString("es-ES");
  const opinionsTotalPrincipalLabel = responseTotalsPrincipal.opinionsTotal.toLocaleString("es-ES");
  const answeredTotalComparisonLabel =
    splitResponsesByActor && responseTotalsComparison
      ? responseTotalsComparison.answeredTotal.toLocaleString("es-ES")
      : null;
  const opinionsTotalComparisonLabel =
    splitResponsesByActor && responseTotalsComparison
      ? responseTotalsComparison.opinionsTotal.toLocaleString("es-ES")
      : null;
  const responseCoveragePrincipal = formatResponseCoverageFromMentions(responseTotalsPrincipal, {
    includeTotals: responseCoverageIncludeTotals,
  });
  const responseCoverageComparison = responseTotalsComparison
    ? formatResponseCoverageFromMentions(responseTotalsComparison, {
        includeTotals: responseCoverageIncludeTotals,
      })
    : null;
  const headerEyebrow = isDashboard
    ? "Dashboard"
    : isSentimentMarkets
      ? "Sentimiento Markets"
      : isSentimentPress
        ? "Sentimiento Prensa"
        : "Panorama reputacional";
  const headerTitle = isDashboard
    ? "Dashboard reputacional"
    : isSentimentMarkets
      ? "Sentimiento en Markets"
      : isSentimentPress
        ? "Sentimiento en Prensa"
        : "Sentimiento histórico";
  const headerSubtitle =
    isDashboard
      ? "Señales de percepción y salud operativa en un mismo vistazo."
      : isSentimentMarkets
        ? "Analiza conversación en app stores y marketplaces. Incluye bloque de opiniones del market contestadas."
        : isSentimentPress
          ? "Analiza conversación en prensa, social, foros y blogs (sin bloque de opiniones contestadas)."
      : comparisonsEnabled
        ? "Analiza la conversación por país, periodo y fuente. Detecta señales tempranas y compara impacto entre entidades."
        : "Analiza la conversación por país, periodo y fuente para el actor principal.";

  return (
    <Shell>
      <section className="relative overflow-hidden rounded-[28px] border border-[color:var(--border-60)] bg-[color:var(--panel-strong)] p-6 shadow-[var(--shadow-lg)] animate-rise">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-24 -right-10 h-48 w-48 rounded-full bg-[color:var(--aqua)]/15 blur-3xl" />
          <div className="absolute -bottom-16 left-10 h-40 w-40 rounded-full bg-[color:var(--blue)]/10 blur-3xl" />
        </div>
        <div className="relative">
          <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-[color:var(--blue)] shadow-sm">
            <Sparkles className="h-3.5 w-3.5" />
            {headerEyebrow}
          </div>
          <h1 className="mt-4 text-3xl sm:text-4xl font-display font-semibold text-[color:var(--ink)]">
            {headerTitle}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[color:var(--text-60)]">
            {headerSubtitle}
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-[color:var(--text-55)]">
            {isDashboard ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-[color:var(--surface-70)] px-1.5 py-1 shadow-[var(--shadow-soft)]">
                <button
                  type="button"
                  onClick={handleDashboardPrevMonth}
                  aria-label="Mes anterior"
                  title="Mes anterior"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-85)] text-[color:var(--blue)] transition hover:bg-[color:var(--surface-70)]"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span
                  data-testid="dashboard-month-label"
                  className="px-2 text-sm sm:text-base font-display font-semibold tracking-[0.08em] text-[color:var(--ink)]"
                >
                  <Calendar className="mr-2 inline-block h-4 w-4 text-[color:var(--blue)]" />
                  {dashboardMonthLabel}
                </span>
                <button
                  type="button"
                  onClick={handleDashboardNextMonth}
                  aria-label="Mes siguiente"
                  title={canGoDashboardNext ? "Mes siguiente" : "Mes actual"}
                  disabled={!canGoDashboardNext}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-85)] text-[color:var(--blue)] transition hover:bg-[color:var(--surface-70)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </span>
            ) : (
              <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
                <Calendar className="h-3.5 w-3.5 text-[color:var(--blue)]" />
                Rango: {rangeLabel}
              </span>
            )}
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <MessageSquare className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Menciones:{" "}
              {itemsLoading ? (
                <LoadingPill className="h-2 w-12" label="Cargando menciones" />
              ) : (
                formatVsValue(mentionsSummaryPrincipal, mentionsSummaryComparison)
              )}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Clock className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Última actualización:{" "}
              {itemsLoading ? (
                <LoadingPill className="h-2 w-16" label="Cargando fecha" />
              ) : (
                latestLabel
              )}
            </span>
            {filterRestoredAt && (
              <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--aqua)]/40 bg-[color:var(--aqua)]/10 px-3 py-1 text-[color:var(--brand-ink)] animate-rise">
                <Sparkles className="h-3.5 w-3.5" />
                Filtros restaurados
              </span>
            )}
          </div>
        </div>
      </section>

      {showCacheNotice && (
        <div className="mt-4 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--panel)] px-4 py-3 text-sm text-[color:var(--text-60)] shadow-[var(--shadow-soft)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-[color:var(--ink)]">
                Sin cache de reputación
              </div>
              <div className="text-xs text-[color:var(--text-55)]">
                Aún no hay datos disponibles. Lanza una ingesta para generar el histórico.
              </div>
              {reputationIngestNote && (
                <div className="mt-1 text-[10px] text-[color:var(--text-50)]">
                  {reputationIngestNote}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={handleStartReputationIngest}
              disabled={reputationIngesting}
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--ink)] transition hover:shadow-[var(--shadow-soft)] disabled:opacity-70"
            >
              {reputationIngesting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Iniciar ingesta
            </button>
          </div>
        </div>
      )}

      {errorMessage && (
        <div className="mt-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {errorMessage}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-4">
        <div className={isDashboard ? "flex h-full flex-col gap-4" : undefined}>
          <section
            className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise"
            style={{ animationDelay: "120ms" }}
          >
            <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
              FILTROS PRINCIPALES
            </div>
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
              {!isDashboard && (
                <FilterField label="Desde">
                  <input
                    type="date"
                    value={fromDate}
                    onChange={(e) => {
                      touchCommonFilters();
                      setFromDate(e.target.value);
                    }}
                    className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
                  />
                </FilterField>
              )}
              {!isDashboard && (
                <FilterField label="Hasta">
                  <input
                    type="date"
                    value={toDate}
                    onChange={(e) => {
                      touchCommonFilters();
                      setToDate(e.target.value);
                    }}
                    className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
                  />
                </FilterField>
              )}
              <FilterField label="Entidad">
                <div className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)]">
                  {actorPrincipalName}
                </div>
              </FilterField>
              {!isDashboard && (
                <FilterField label="Sentimiento">
                  <select
                    value={sentiment}
                    onChange={(e) => {
                      touchCommonFilters();
                      setSentiment(e.target.value as SentimentFilter);
                    }}
                    className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
                  >
                    {SENTIMENTS.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt === "all" ? "Todos" : opt}
                      </option>
                    ))}
                  </select>
                </FilterField>
              )}
              <FilterField label="País">
                <select
                  value={geo}
                  onChange={(e) => {
                    touchCommonFilters();
                    setGeo(e.target.value);
                  }}
                  className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
                >
                  <option value="all">Todos</option>
                  {geoOptions.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </FilterField>
              {!isDashboard && comparisonsEnabled && (
                <FilterField label="Otros actores del mercado">
                  <select
                    value={actor}
                    onChange={(e) => {
                      touchItemsFilters();
                      setActor(e.target.value);
                    }}
                    className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30 disabled:opacity-60"
                  >
                    <option value="all">Todos</option>
                    {actorOptions.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                </FilterField>
              )}
            </div>

            <div className="mt-4">
              <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                FUENTES
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {sourcesOptions.map((src) => {
                  const active = sources.includes(src);
                  const count = sourceCounts[src];
                  const sourceCount = isDashboard ? count?.total : count?.principal;
                  const countPrincipalLabel = sourceCount?.toLocaleString("es-ES");
                  const countComparisonLabel =
                    count && !isDashboard && comparisonsEnabled
                      ? count.others.toLocaleString("es-ES")
                      : null;
                  return (
                    <button
                      key={src}
                      onClick={() => {
                        touchCommonFilters();
                        toggleSource(src, sources, setSources);
                      }}
                      className={
                        "rounded-full px-3 py-1.5 text-xs border transition shadow-sm " +
                        (active
                          ? "bg-[color:var(--blue)] text-white border-transparent"
                          : "bg-[color:var(--surface-80)] text-[color:var(--brand-ink)] border-[color:var(--border-60)]")
                      }
                    >
                      <span>{src}</span>
                      {countPrincipalLabel && !itemsLoading && (
                        <span
                          className={
                            "ml-2 rounded-full px-2 py-0.5 text-[10px] font-semibold " +
                            (active
                              ? "bg-[color:var(--surface-15)] text-white"
                              : "bg-[color:var(--sand)] text-[color:var(--brand-ink)]")
                          }
                        >
                          {formatVsValue(countPrincipalLabel, countComparisonLabel)}
                        </span>
                      )}
                      {itemsLoading && (
                        <LoadingPill
                          className={
                            "ml-2 h-2 w-6 " +
                            (active
                              ? "border-[color:var(--surface-15)]"
                              : "border-[color:var(--border-60)]")
                          }
                          label={`Cargando ${src}`}
                        />
                      )}
                    </button>
                  );
                })}
                {!sourcesOptions.length && (
                  <span className="text-xs text-[color:var(--text-40)]">
                    Sin datos disponibles
                  </span>
                )}
              </div>
            </div>
          </section>

          {!isDashboard && !isSentimentPress && (
            <section
              className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise"
              style={{ animationDelay: "180ms" }}
            >
              <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                ACTORES DEL MERCADO
              </div>
              <div className="mt-2 space-y-2">
                {itemsLoading ? (
                  <SkeletonRows count={4} />
                ) : !marketActorRows.length ? (
                  <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                    Sin datos disponibles
                  </div>
                ) : (
                  (() => {
                    const maxValue = Math.max(1, ...marketActorRows.map((row) => row.count));
                    return marketActorRows.map((row) => (
                      <MarketActorRowMeter
                        key={row.key}
                        label={row.label}
                        value={row.count}
                        maxValue={maxValue}
                        sourceCounts={row.sourceCounts}
                      />
                    ));
                  })()
                )}
              </div>
              {!itemsLoading && (
                <div className="mt-3">
                  <MarketActorSourcesLegend sourceTotals={marketSourceTotals} />
                </div>
              )}
            </section>
          )}

          {showPressPublishersBlock && (
            <section
              className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise"
              style={{ animationDelay: "210ms" }}
            >
              <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                MEDIOS EN PRENSA
              </div>
              <div className="mt-2 space-y-2">
                {itemsLoading ? (
                  <SkeletonRows count={4} />
                ) : !pressPublisherRows.length ? (
                  <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                    Sin datos disponibles
                  </div>
                ) : (
                  (() => {
                    const maxValue = Math.max(1, ...pressPublisherRows.map((row) => row.count));
                    return pressPublisherRows.slice(0, 12).map((row) => (
                      <PressPublisherRowMeter
                        key={row.key}
                        label={row.label}
                        value={row.count}
                        maxValue={maxValue}
                        sourceCounts={row.sourceCounts}
                      />
                    ));
                  })()
                )}
              </div>
              {!itemsLoading && (
                <div className="mt-3">
                  <PressPublisherSourcesLegend sourceTotals={pressPublisherSourceTotals} />
                </div>
              )}
            </section>
          )}

          {isDashboard && (
            <section
              className="flex-1 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise"
              style={{ animationDelay: "240ms" }}
            >
              <h2 className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                MAPA DE CALOR DE OPINIONES NEGATIVAS EN LOS MARKETS
              </h2>
              <p className="mt-2 text-xs text-[color:var(--text-55)]">
                Dónde se concentra la negatividad y con qué intensidad.
              </p>
              <div className="mt-4 space-y-3">
                {dashboardMarketInsightsLoading && (
                  <div className="space-y-2">
                    <LoadingPill className="h-3 w-28" label="Cargando canales" />
                    <LoadingPill className="h-3 w-full" label="Cargando canales" />
                  </div>
                )}
                {!dashboardMarketInsightsLoading && dashboardMarketInsightsError && (
                  <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                    No se pudo cargar el mapa de calor de los markets.
                  </div>
                )}
                {!dashboardMarketInsightsLoading &&
                  !dashboardMarketInsightsError &&
                  !dashboardHeatSources.length && (
                    <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                      Sin datos para el periodo.
                    </div>
                  )}
                {!dashboardMarketInsightsLoading &&
                  !dashboardMarketInsightsError &&
                  dashboardHeatSources.slice(0, 10).map((source) => (
                    <div
                      key={source.source}
                      className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm text-[color:var(--ink)]">{source.source}</div>
                        <div className="text-xs text-[color:var(--text-55)]">
                          {source.negative} negativas ({formatRatioPercent(source.negative_ratio)})
                        </div>
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-[color:var(--surface-60)] overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-rose-400/80 to-amber-300/80"
                          style={{ width: `${Math.min(Math.max(source.negative_ratio * 100, 0), 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                {!dashboardMarketInsightsLoading &&
                  !dashboardMarketInsightsError &&
                  dashboardHeatDenominator > 0 && (
                    <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-xs text-[color:var(--text-55)]">
                      Base:{" "}
                      <span className="font-semibold text-[color:var(--ink)]">
                        {dashboardHeatDenominator.toLocaleString("es-ES")}
                      </span>{" "}
                      opiniones contestables (App Store + Google Play).
                    </div>
                  )}
              </div>
            </section>
          )}
        </div>

        <section
          className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise"
          style={{ animationDelay: "180ms" }}
        >
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
            RESUMEN
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {isDashboard ? (
              <>
                <PrincipalMentionsCard
                  totalMentions={mentionsSummaryPrincipal}
                  positiveMentions={positivesSummaryPrincipal}
                  neutralMentions={neutralsSummaryPrincipal}
                  negativeMentions={negativesSummaryPrincipal}
                  actorName={actorPrincipalName}
                  periodLabel={mentionsPeriodLabel}
                  loading={itemsLoading}
                />
                <div className="col-span-2">
                  <StoreRatingCard
                    label="Rating oficial"
                    ratings={principalStoreRatings}
                    loading={itemsLoading}
                    visibility={storeRatingVisibility}
                    history={marketRatingsHistory}
                    layout="columns"
                  />
                </div>
              </>
            ) : isSentimentMarkets || isSentimentPress ? (
              <>
                <PrincipalMentionsCard
                  title={actorPrincipalName}
                  showActorLine={false}
                  totalMentions={mentionsSummaryPrincipal}
                  positiveMentions={positivesSummaryPrincipal}
                  neutralMentions={neutralsSummaryPrincipal}
                  negativeMentions={negativesSummaryPrincipal}
                  actorName={actorPrincipalName}
                  periodLabel={mentionsPeriodLabel}
                  loading={itemsLoading}
                />
                {selectedActor && (
                  <PrincipalMentionsCard
                    title={selectedMarketActorLabel}
                    showActorLine={false}
                    totalMentions={selectedActorMentionsTotalLabel}
                    positiveMentions={selectedActorMentionsSummary.positive}
                    neutralMentions={selectedActorMentionsSummary.neutral}
                    negativeMentions={selectedActorMentionsSummary.negative}
                    actorName={selectedMarketActorLabel}
                    periodLabel={mentionsPeriodLabel}
                    loading={itemsLoading}
                  />
                )}
                {isSentimentMarkets && showStoreRatingsForGeo && (
                  <StoreRatingCard
                    label={actorPrincipalName}
                    ratings={principalStoreRatings}
                    loading={itemsLoading}
                    visibility={storeRatingVisibility}
                    history={marketRatingsHistory}
                  />
                )}
                {isSentimentMarkets && showStoreRatingsForGeo && comparisonsEnabled && (
                  <StoreRatingCard
                    label={selectedMarketActorLabel}
                    ratings={actorStoreRatings}
                    loading={itemsLoading}
                    visibility={storeRatingVisibility}
                    history={marketRatingsHistory}
                    emptyLabel="Selecciona actor"
                  />
                )}
              </>
            ) : (
              <>
                <SummaryCard
                  label="Total menciones"
                  value={formatVsValue(mentionsSummaryPrincipal, mentionsSummaryComparison)}
                  loading={itemsLoading}
                />
                <SummaryCard
                  label="Score medio"
                  value={formatVsValue(scoreSummaryPrincipal, scoreSummaryComparison)}
                  loading={itemsLoading}
                />
                {showStoreRatingsForGeo && (
                  <StoreRatingCard
                    label="Rating oficial"
                    ratings={principalStoreRatings}
                    loading={itemsLoading}
                    visibility={storeRatingVisibility}
                    history={marketRatingsHistory}
                  />
                )}
                {showStoreRatingsForGeo && comparisonsEnabled && (
                  <StoreRatingCard
                    label="Rating oficial otros actores"
                    ratings={actorStoreRatings}
                    loading={itemsLoading}
                    visibility={storeRatingVisibility}
                    history={marketRatingsHistory}
                    emptyLabel="Selecciona actor"
                  />
                )}
                <SummaryCard
                  label="Positivas"
                  value={formatVsValue(positivesSummaryPrincipal, positivesSummaryComparison)}
                  loading={itemsLoading}
                />
                <SummaryCard
                  label="Negativas"
                  value={formatVsValue(negativesSummaryPrincipal, negativesSummaryComparison)}
                  loading={itemsLoading}
                />
              </>
            )}
            {showResponsesSummary && (
              <>
                <div className="col-span-2 relative overflow-hidden rounded-2xl border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-4 py-3 shadow-[var(--shadow-soft)]">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[color:var(--aqua)] via-[color:var(--blue)] to-transparent" />
                  <div
                    data-testid="responses-summary-title"
                    className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-45)]"
                  >
                    {responseSummaryUsesRatios ? (
                      isSentimentMarkets ? (
                        <>
                          <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
                            {actorPrincipalName}
                          </div>
                          <div className="mt-1">
                            <span className="inline-flex items-end gap-1">
                              <span className="text-2xl font-display font-semibold leading-none text-[color:var(--ink)]">
                                {answeredTotalPrincipalLabel}
                              </span>
                              <span className="pb-0.5 text-base font-semibold leading-none text-[color:var(--text-45)]">
                                /{opinionsTotalPrincipalLabel}
                              </span>
                              <span className="pb-0.5">opiniones del market contestadas</span>
                            </span>
                          </div>
                        </>
                      ) : (
                        <span className="inline-flex items-end gap-1">
                          <span className="text-2xl font-display font-semibold leading-none text-[color:var(--ink)]">
                            {answeredTotalPrincipalLabel}
                          </span>
                          <span className="pb-0.5 text-base font-semibold leading-none text-[color:var(--text-45)]">
                            /{opinionsTotalPrincipalLabel}
                          </span>
                          <span className="pb-0.5">opiniones del market contestadas</span>
                        </span>
                      )
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        {formatVsValue(answeredTotalPrincipalLabel, answeredTotalComparisonLabel, {
                          containerClassName: "inline-flex items-center whitespace-nowrap",
                          vsClassName:
                            "mx-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-45)]",
                        })}
                        <span>opiniones contestadas</span>
                      </span>
                    )}
                  </div>
                  {!isSentimentMarkets && (
                    <div className="mt-1 text-[10px] text-[color:var(--text-55)]">
                      {formatVsValue(actorPrincipalName, splitResponsesByActor ? actorLabel : null, {
                        containerClassName: "inline-flex items-center whitespace-nowrap",
                        vsClassName:
                          "mx-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-45)]",
                      })}
                    </div>
                  )}
                  {mentionsLoading ? (
                    <div className="mt-3 space-y-2">
                      <LoadingPill className="h-4 w-28" label="Cargando respuestas" />
                      <LoadingPill className="h-3 w-full" label="Cargando respuestas" />
                    </div>
                  ) : (
                    <>
                      <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                        <ResponseStat
                          label="Positivas"
                          value={responseTotalsPrincipal.answeredPositive}
                          denominator={
                            responseSummaryUsesRatios ? responseTotalsPrincipal.opinionsPositive : null
                          }
                          comparisonValue={
                            isSentimentMarkets ? null : responseTotalsComparison?.answeredPositive ?? null
                          }
                          comparisonDenominator={
                            responseSummaryUsesRatios
                              ? responseTotalsComparison?.opinionsPositive ?? null
                              : null
                          }
                          prominentRatio={responseSummaryUsesRatios}
                        />
                        <ResponseStat
                          label="Neutras"
                          value={responseTotalsPrincipal.answeredNeutral}
                          denominator={
                            responseSummaryUsesRatios ? responseTotalsPrincipal.opinionsNeutral : null
                          }
                          comparisonValue={
                            isSentimentMarkets ? null : responseTotalsComparison?.answeredNeutral ?? null
                          }
                          comparisonDenominator={
                            responseSummaryUsesRatios
                              ? responseTotalsComparison?.opinionsNeutral ?? null
                              : null
                          }
                          prominentRatio={responseSummaryUsesRatios}
                        />
                        <ResponseStat
                          label="Negativas"
                          value={responseTotalsPrincipal.answeredNegative}
                          denominator={
                            responseSummaryUsesRatios ? responseTotalsPrincipal.opinionsNegative : null
                          }
                          comparisonValue={
                            isSentimentMarkets ? null : responseTotalsComparison?.answeredNegative ?? null
                          }
                          comparisonDenominator={
                            responseSummaryUsesRatios
                              ? responseTotalsComparison?.opinionsNegative ?? null
                              : null
                          }
                          prominentRatio={responseSummaryUsesRatios}
                        />
                      </div>
                      <div className="mt-2 text-[11px] text-[color:var(--text-55)]">
                        Cobertura de respuesta:{" "}
                        {isSentimentMarkets
                          ? responseCoveragePrincipal
                          : formatVsValue(responseCoveragePrincipal, responseCoverageComparison, {
                              containerClassName: "inline-flex items-center whitespace-nowrap",
                              vsClassName:
                                "mx-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-45)]",
                            })}
                      </div>
                    </>
                  )}
                </div>
                {showSecondaryMarketResponses && responseTotalsComparison && (
                  <div className="col-span-2 relative overflow-hidden rounded-2xl border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-4 py-3 shadow-[var(--shadow-soft)]">
                    <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[color:var(--aqua)] via-[color:var(--blue)] to-transparent" />
                    <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
                      {selectedMarketActorLabel}
                    </div>
                    <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
                      <span className="inline-flex items-end gap-1">
                        <span className="text-2xl font-display font-semibold leading-none text-[color:var(--ink)]">
                          {answeredTotalComparisonLabel}
                        </span>
                        <span className="pb-0.5 text-base font-semibold leading-none text-[color:var(--text-45)]">
                          /{opinionsTotalComparisonLabel}
                        </span>
                        <span className="pb-0.5">opiniones del market contestadas</span>
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                      <ResponseStat
                        label="Positivas"
                        value={responseTotalsComparison.answeredPositive}
                        denominator={responseTotalsComparison.opinionsPositive}
                        prominentRatio
                      />
                      <ResponseStat
                        label="Neutras"
                        value={responseTotalsComparison.answeredNeutral}
                        denominator={responseTotalsComparison.opinionsNeutral}
                        prominentRatio
                      />
                      <ResponseStat
                        label="Negativas"
                        value={responseTotalsComparison.answeredNegative}
                        denominator={responseTotalsComparison.opinionsNegative}
                        prominentRatio
                      />
                    </div>
                    <div className="mt-2 text-[11px] text-[color:var(--text-55)]">
                      Cobertura de respuesta: {responseCoverageComparison}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      </div>

      <section className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "300ms" }}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
            {mode === "dashboard" ? "SENTIMIENTO" : "ÍNDICE REPUTACIONAL ACUMULADO"}
          </div>
          <div className="text-xs text-[color:var(--text-55)]">
            {mode === "dashboard"
              ? `${principalLabel} · ${dashboardMonthLabel}`
              : comparisonsEnabled
                ? (
                    <>
                      Comparativa{" "}
                      {formatVsValue(principalLabel, actorLabel, {
                        containerClassName: "inline-flex items-center whitespace-nowrap",
                        vsClassName:
                          "mx-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-45)]",
                      })}{" "}
                      · {rangeLabel}
                    </>
                  )
                : `${principalLabel} · ${rangeLabel}`}
          </div>
        </div>
        {showDownloads && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <button
              onClick={() =>
                downloadChartCsv(
                  sentimentSeries,
                  principalLabel,
                  actorLabel,
                  buildDownloadName("sentimiento_grafico", fromDate, toDate),
                  comparisonsEnabled,
                )
              }
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--brand-ink)] shadow-[var(--shadow-pill)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pill-hover)]"
            >
              Descargar gráfico
            </button>
          </div>
        )}
        <div
          ref={chartSectionRef}
          className="mt-3 h-72 min-h-[240px]"
        >
          {!chartsVisible ? (
            <div className="h-full rounded-[22px] border border-[color:var(--border-60)] bg-[color:var(--surface-70)] animate-pulse" />
          ) : chartLoading ? (
            <div className="h-full rounded-[22px] border border-[color:var(--border-60)] bg-[color:var(--surface-70)] animate-pulse" />
          ) : mode === "dashboard" ? (
            <DashboardChart
              data={dashboardSeries}
              sentimentLabel={principalLabel}
            />
          ) : (
            <SentimentChart
              data={sentimentSeries}
              principalLabel={principalLabel}
              actorLabel={actorLabel}
              showActor={comparisonsEnabled}
            />
          )}
        </div>
      </section>


      {mode === "dashboard" ? (
        <>
          <section
            className="mt-6 grid grid-cols-1 xl:grid-cols-[1.2fr_1fr] gap-4 animate-rise"
            style={{ animationDelay: "360ms" }}
          >
            <article className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl">
              <h2 className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                TOP 10 FUNCIONALIDADES PENALIZADAS
              </h2>
              <p className="mt-2 text-xs text-[color:var(--text-55)]">
                Ranking de fricción en opiniones negativas del periodo seleccionado.
              </p>
              <div className="mt-4 space-y-3">
                {dashboardMarketInsightsLoading && (
                  <div className="space-y-2">
                    <LoadingPill className="h-3 w-40" label="Cargando funcionalidades" />
                    <LoadingPill className="h-3 w-full" label="Cargando funcionalidades" />
                  </div>
                )}
                {!dashboardMarketInsightsLoading && dashboardMarketInsightsError && (
                  <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                    No se pudo cargar funcionalidades penalizadas para el dashboard.
                  </div>
                )}
                {!dashboardMarketInsightsLoading &&
                  !dashboardMarketInsightsError &&
                  !dashboardTopPenalizedFeatures.length && (
                    <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                      No hay volumen negativo suficiente para construir ranking.
                    </div>
                  )}
                {!dashboardMarketInsightsLoading &&
                  !dashboardMarketInsightsError &&
                  dashboardTopPenalizedFeatures.map((entry, index) => (
                    <div
                      key={entry.key}
                      className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm text-[color:var(--ink)]">
                          {index + 1}. {entry.feature}
                        </div>
                        <span className="text-xs text-[color:var(--text-55)]">{entry.count}</span>
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-[color:var(--surface-60)] overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-[color:var(--aqua)] to-[color:var(--blue)]"
                          style={{ width: `${(entry.count / dashboardMaxFeatureCount) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
              </div>
            </article>

            <article className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl">
              <h2 className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                ALERTAS CALIENTES
              </h2>
              <p className="mt-2 text-xs text-[color:var(--text-55)]">
                Señales críticas para activar respuesta inmediata.
              </p>
              <div className="mt-4 space-y-3">
                {dashboardMarketInsightsLoading && (
                  <div className="space-y-2">
                    <LoadingPill className="h-3 w-24" label="Cargando alertas" />
                    <LoadingPill className="h-3 w-full" label="Cargando alertas" />
                  </div>
                )}
                {!dashboardMarketInsightsLoading && dashboardMarketInsightsError && (
                  <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                    No se pudieron cargar alertas para el dashboard.
                  </div>
                )}
                {!dashboardMarketInsightsLoading &&
                  !dashboardMarketInsightsError &&
                  !dashboardAlerts.length && (
                    <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                      Sin alertas críticas en este corte.
                    </div>
                  )}
                {!dashboardMarketInsightsLoading &&
                  !dashboardMarketInsightsError &&
                  dashboardAlerts.map((alert) => (
                    <div
                      key={alert.id}
                      className={`rounded-xl border px-3 py-2 ${marketAlertTone(alert.severity)}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-xs uppercase tracking-[0.18em]">{alert.severity}</div>
                        <AlertTriangle className="h-4 w-4" />
                      </div>
                      <div className="mt-1 text-sm font-semibold">{alert.title}</div>
                      <div className="mt-1 text-xs opacity-90">{alert.summary}</div>
                    </div>
                  ))}
              </div>
            </article>
          </section>
        </>
      ) : (
        <section className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "360ms" }}>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                LISTADO
              </div>
              <div className="mt-1 text-[11px] text-[color:var(--text-55)]">
                {listedFiltersLabel}
              </div>
            </div>
            <div className="text-xs text-[color:var(--text-50)] sm:text-right">
              {mentionsLoading ? (
                <LoadingPill className="h-2 w-24" label="Cargando resultados" />
              ) : (
                <>
                  Mostrando {mentionsToShow.length} resultados · {mentionsLabel}
                </>
              )}
            </div>
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2 rounded-[22px] border border-[color:var(--border-70)] bg-[color:var(--surface-70)] p-1.5 shadow-[var(--shadow-soft)]">
              <button
                onClick={() => setMentionsTab("principal")}
                className={
                  "group w-full sm:w-auto flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2 rounded-full px-3 py-1.5 text-xs font-semibold transition sm:hover:-translate-y-0.5 " +
                  (effectiveMentionsTab === "principal"
                    ? "bg-[color:var(--surface-solid)] text-[color:var(--ink)] shadow-[var(--shadow-sm)] ring-1 ring-[color:var(--aqua)]/30"
                    : "text-[color:var(--text-50)] hover:text-[color:var(--ink)] hover:bg-[color:var(--surface-80)]")
                }
              >
                <span className="flex items-center gap-2">
                  <span className="inline-block h-1.5 w-7 rounded-full bg-[#004481]" />
                  {principalLabel}
                </span>
                <span className="flex items-center gap-2 text-[10px] text-[color:var(--text-40)]">
                  {principalMentions.length} resultados
                  <span className="hidden sm:flex items-center gap-1 text-[9px] uppercase tracking-[0.2em] text-[color:var(--text-40)] opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
                    <ArrowUpRight className="h-3 w-3" />
                    Clic
                  </span>
                </span>
              </button>
              {comparisonsEnabled && (
                <button
                  onClick={() => setMentionsTab("actor")}
                  className={
                    "group w-full sm:w-auto flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2 rounded-full px-3 py-1.5 text-xs font-semibold transition sm:hover:-translate-y-0.5 " +
                    (effectiveMentionsTab === "actor"
                      ? "bg-[color:var(--surface-solid)] text-[color:var(--ink)] shadow-[var(--shadow-sm)] ring-1 ring-[color:var(--aqua)]/30"
                      : "text-[color:var(--text-50)] hover:text-[color:var(--ink)] hover:bg-[color:var(--surface-80)]")
                  }
                >
                  <span className="flex items-center gap-2">
                    <span className="inline-block h-[3px] w-7 rounded-full border-t-2 border-dashed border-[#2dcccd]" />
                    {actorLabel}
                  </span>
                  <span className="flex items-center gap-2 text-[10px] text-[color:var(--text-40)]">
                    {actorMentions.length} resultados
                    <span className="hidden sm:flex items-center gap-1 text-[9px] uppercase tracking-[0.2em] text-[color:var(--text-40)] opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
                      <ArrowUpRight className="h-3 w-3" />
                      Clic
                    </span>
                  </span>
                </button>
              )}
            </div>
            {showDownloads && (
              <button
                onClick={() =>
                  downloadMentionsWorkbook({
                    principalItems: principalMentions,
                    actorItems: actorMentions,
                    principalLabel,
                    actorLabel,
                    filename: buildDownloadName("sentimiento_listado", fromDate, toDate),
                    activeTab: effectiveMentionsTab,
                    includeActorSheet: comparisonsEnabled,
                  })
                }
                className="inline-flex w-full sm:w-auto items-center justify-center gap-2 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--brand-ink)] shadow-[var(--shadow-pill)] transition sm:hover:-translate-y-0.5 hover:shadow-[var(--shadow-pill-hover)] sm:ml-auto"
              >
                Descargar listado
              </button>
            )}
          </div>
          <div className="mt-4 space-y-3">
            {mentionsLoading && (
              <div className="text-sm text-[color:var(--text-50)]">Cargando sentimiento…</div>
            )}
            {!mentionsLoading &&
              mentionsToShow.map((item, index) => (
                <MentionCard
                  key={item.key}
                  item={item}
                  index={index}
                  principalLabel={actorPrincipalName}
                  geoOptions={geoOptions}
                  manualControlsEnabled={!isSentimentMarkets}
                  onOverride={handleOverride}
                />
              ))}
            {!mentionsLoading && !mentionsToShow.length && (
              <div className="text-sm text-[color:var(--text-45)]">
                No hay menciones para mostrar.
              </div>
            )}
          </div>
        </section>
      )}
    </Shell>
  );
}

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-50)]">
      <span className="block mb-2">{label}</span>
      {children}
    </label>
  );
}

function LoadingPill({
  className = "",
  label = "Cargando",
}: {
  className?: string;
  label?: string;
}) {
  return (
    <span
      className={`shimmer inline-block rounded-full border border-[color:var(--border-60)] ${className}`}
    >
      <span className="sr-only">{label}</span>
    </span>
  );
}

function SummaryCard({
  label,
  value,
  loading = false,
  className = "",
}: {
  label: string;
  value: ReactNode;
  loading?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`relative overflow-hidden rounded-2xl border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-4 py-3 shadow-[var(--shadow-soft)] ${className}`.trim()}
    >
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[color:var(--aqua)] via-[color:var(--blue)] to-transparent" />
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
        {label}
      </div>
      <div className="mt-2 text-2xl font-display font-semibold text-[color:var(--ink)]">
        {loading ? (
          <LoadingPill className="h-6 w-24" label={`Cargando ${label}`} />
        ) : (
          value
        )}
      </div>
    </div>
  );
}

function PrincipalMentionsCard({
  title = "Menciones actor principal",
  showActorLine = true,
  totalMentions,
  positiveMentions,
  neutralMentions,
  negativeMentions,
  actorName,
  periodLabel,
  loading = false,
}: {
  title?: string;
  showActorLine?: boolean;
  totalMentions: ReactNode;
  positiveMentions: ReactNode;
  neutralMentions: ReactNode;
  negativeMentions: ReactNode;
  actorName: string;
  periodLabel: string;
  loading?: boolean;
}) {
  return (
    <div className="col-span-2 relative overflow-hidden rounded-2xl border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-4 py-3 shadow-[var(--shadow-soft)]">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[color:var(--aqua)] via-[color:var(--blue)] to-transparent" />
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
        {title}
      </div>
      {loading ? (
        <div className="mt-3 space-y-2">
          <LoadingPill className="h-6 w-28" label={`Cargando ${title}`} />
          <LoadingPill className="h-3 w-full" label={`Cargando ${title}`} />
        </div>
      ) : (
        <>
          {showActorLine && (
            <div className="mt-1 text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
              {actorName}
            </div>
          )}
          <div className="mt-1 text-2xl font-display font-semibold text-[color:var(--ink)]">
            {totalMentions}
            <span className="ml-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-45)]">
              {`menciones del ${periodLabel}`.toUpperCase()}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3 text-xs">
            <ResponseStat label="Positivas" value={toNumberOrZero(positiveMentions)} />
            <ResponseStat label="Neutras" value={toNumberOrZero(neutralMentions)} />
            <ResponseStat label="Negativas" value={toNumberOrZero(negativeMentions)} />
          </div>
        </>
      )}
    </div>
  );
}

function toNumberOrZero(value: ReactNode): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const normalized = value.replace(/\./g, "").replace(",", ".");
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function formatCountRatioLabel(value: number, denominator?: number | null): string {
  const numeratorLabel = value.toLocaleString("es-ES");
  if (typeof denominator !== "number") return numeratorLabel;
  return `${numeratorLabel}/${denominator.toLocaleString("es-ES")}`;
}

function formatCountRatioValue(
  value: number,
  denominator: number | null | undefined,
  prominentRatio: boolean,
): ReactNode {
  if (!prominentRatio || typeof denominator !== "number") {
    return formatCountRatioLabel(value, denominator);
  }
  return (
    <span className="inline-flex items-end whitespace-nowrap">
      <span className="text-2xl font-display font-semibold leading-none text-[color:var(--ink)]">
        {value.toLocaleString("es-ES")}
      </span>
      <span className="ml-0.5 pb-0.5 text-xs font-semibold leading-none text-[color:var(--text-45)]">
        /{denominator.toLocaleString("es-ES")}
      </span>
    </span>
  );
}

function ResponseStat({
  label,
  value,
  denominator = null,
  comparisonValue = null,
  comparisonDenominator = null,
  prominentRatio = false,
}: {
  label: string;
  value: number;
  denominator?: number | null;
  comparisonValue?: number | null;
  comparisonDenominator?: number | null;
  prominentRatio?: boolean;
}) {
  const principal = formatCountRatioValue(value, denominator, prominentRatio);
  const comparison =
    typeof comparisonValue === "number"
      ? formatCountRatioValue(comparisonValue, comparisonDenominator, prominentRatio)
      : null;
  return (
    <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-2 py-1.5 text-center">
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
        {label}
      </div>
      <div className={`mt-1 ${prominentRatio ? "text-base" : "text-sm"} font-semibold text-[color:var(--ink)]`}>
        {formatVsValue(principal, comparison, {
          containerClassName: "inline-flex items-center justify-center whitespace-nowrap",
          vsClassName:
            "mx-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-45)]",
        })}
      </div>
    </div>
  );
}

function StoreRatingCard({
  label,
  subtitle,
  ratings,
  loading = false,
  visibility,
  emptyLabel = "—",
  history,
  layout = "stack",
}: {
  label: string;
  subtitle?: string;
  ratings: ActorStoreRatings | null;
  loading?: boolean;
  visibility: { showApple: boolean; showGoogle: boolean };
  emptyLabel?: string;
  history?: MarketRating[];
  layout?: "stack" | "columns";
}) {
  const showApple = visibility.showApple;
  const showGoogle = visibility.showGoogle;
  const rows = [
    showApple
      ? {
          key: "apple",
          icon: <AppleMark className="h-5 w-5" />,
          current: ratings?.appstore ?? null,
          tone: "apple" as const,
          platformLabel: "Apple",
        }
      : null,
    showGoogle
      ? {
          key: "google",
          icon: <AndroidMark className="h-5 w-5" />,
          current: ratings?.google_play ?? null,
          tone: "google" as const,
          platformLabel: "Android",
        }
      : null,
  ].filter(Boolean) as Array<{
    key: string;
    icon: ReactNode;
    current: MarketRating | null;
    tone: "apple" | "google";
    platformLabel: string;
  }>;
  const rowsClassName =
    layout === "columns"
      ? "mt-3 mt-auto grid grid-cols-2 gap-2"
      : "mt-3 mt-auto space-y-2";
  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-4 py-3 shadow-[var(--shadow-soft)]">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[color:var(--aqua)] via-[color:var(--blue)] to-transparent" />
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
        {label}
        {subtitle && (
          <div className="mt-1 text-[10px] font-semibold tracking-[0.12em] text-[color:var(--text-55)]">
            {subtitle}
          </div>
        )}
      </div>
      {loading ? (
        <div className="mt-3 space-y-2">
          <LoadingPill className="h-8 w-full" label={`Cargando ${label}`} />
          <LoadingPill className="h-8 w-5/6" label={`Cargando ${label}`} />
        </div>
      ) : !ratings ? (
        <div className="mt-3 text-sm text-[color:var(--text-55)]">{emptyLabel}</div>
      ) : (
        <div className={rowsClassName}>
          {rows.length === 0 && (
            <div className="text-sm text-[color:var(--text-55)]">—</div>
          )}
          {rows.map((row) => (
            <StoreRatingRow
              key={row.key}
              icon={row.icon}
              current={row.current}
              history={history}
              tone={row.tone}
              platformLabel={row.platformLabel}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function StoreRatingRow({
  icon,
  current,
  history,
  tone,
  platformLabel,
}: {
  icon: ReactNode;
  current: MarketRating | null;
  history?: MarketRating[];
  tone: "apple" | "google";
  platformLabel?: string;
}) {
  const value = current?.rating ?? null;
  const hasValue = typeof value === "number" && Number.isFinite(value);
  const trend = getMarketRatingTrend(current, history ?? []);
  const trendTooltip = trend.previous
    ? `Último registro: ${formatDate(trend.previous.collected_at)} · ${trend.previous.rating.toFixed(2)}`
    : "Sin histórico";
  const trendTone =
    trend.status === "up"
      ? "text-emerald-400"
      : trend.status === "down"
        ? "text-rose-400"
        : "text-[color:var(--text-45)]";
  return (
    <div className="group relative grid grid-cols-[28px_1fr_auto] items-center gap-3 rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2">
      <div
        className={
          tone === "apple" ? "text-[color:var(--ink)]" : "text-[color:var(--aqua)]"
        }
      >
        {icon}
      </div>
      <div className="text-right">
        {platformLabel && (
          <div className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--text-45)]">
            {platformLabel}
          </div>
        )}
        <div
          className={`text-lg font-display font-semibold ${
            hasValue ? "text-[color:var(--ink)]" : "text-[color:var(--text-45)]"
          }`}
        >
          {hasValue ? value.toFixed(2) : "—"}
          {hasValue && (
            <span className="ml-1 text-[11px] text-[color:var(--text-45)]">
              /5
            </span>
          )}
        </div>
      </div>
      <span
        title={trendTooltip}
        className={`inline-flex h-5 w-5 items-center justify-center rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-80)] ${trendTone}`}
      >
        {trend.status === "up" && <Triangle className="h-3 w-3" />}
        {trend.status === "down" && <Triangle className="h-3 w-3 rotate-180" />}
        {(trend.status === "flat" || trend.status === "none") && (
          <Minus className="h-3 w-3" />
        )}
      </span>
    </div>
  );
}

function MarketActorRowMeter({
  label,
  value,
  maxValue,
  sourceCounts,
}: {
  label: string;
  value: number;
  maxValue: number;
  sourceCounts: MarketActorSourceCounts;
}) {
  const safeMax = Math.max(1, maxValue);
  const ratio = Math.min(1, Math.max(0, value / safeMax));
  const fillWidthPercent = Math.round(ratio * 100);
  const sourceTotal = MARKET_ACTOR_SOURCE_ORDER.reduce(
    (sum, sourceKey) => sum + sourceCounts[sourceKey],
    0,
  );
  const segments = MARKET_ACTOR_SOURCE_ORDER.filter((sourceKey) => sourceCounts[sourceKey] > 0);
  if (sourceTotal <= 0 || !segments.length) return null;

  return (
    <div className="flex items-center gap-3">
      <div className="w-28 text-xs text-[color:var(--text-55)] truncate">{label}</div>
      <div className="flex-1 h-2 rounded-full bg-[color:var(--surface-70)] overflow-hidden border border-[color:var(--border-70)]">
        <div
          className="flex h-full overflow-hidden rounded-full"
          style={{ width: `${fillWidthPercent}%` }}
        >
          {segments.map((sourceKey) => (
            <div
              key={sourceKey}
              className={`${MARKET_ACTOR_SOURCE_COLOR_CLASS[sourceKey]} h-full`}
              style={{ width: `${(sourceCounts[sourceKey] / sourceTotal) * 100}%` }}
              title={`${MARKET_ACTOR_SOURCE_LABELS[sourceKey]}: ${sourceCounts[sourceKey].toLocaleString("es-ES")}`}
            />
          ))}
        </div>
      </div>
      <div className="w-12 text-right text-xs text-[color:var(--text-55)]">
        {value.toLocaleString("es-ES")}
      </div>
    </div>
  );
}

function MarketActorSourcesLegend({
  sourceTotals,
}: {
  sourceTotals: MarketActorSourceCounts;
}) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-[color:var(--text-55)]">
      <span className="uppercase tracking-[0.14em] text-[color:var(--text-45)]">
        Leyenda:
      </span>
      {MARKET_ACTOR_SOURCE_ORDER.map((sourceKey) => (
        <span key={sourceKey} className="inline-flex items-center gap-1.5">
          <span
            className={`h-2.5 w-2.5 rounded-full ${MARKET_ACTOR_SOURCE_COLOR_CLASS[sourceKey]}`}
          />
          <span>
            {MARKET_ACTOR_SOURCE_LABELS[sourceKey]} (
            {sourceTotals[sourceKey].toLocaleString("es-ES")})
          </span>
        </span>
      ))}
    </div>
  );
}

function PressPublisherRowMeter({
  label,
  value,
  maxValue,
  sourceCounts,
}: {
  label: string;
  value: number;
  maxValue: number;
  sourceCounts: Record<string, number>;
}) {
  const safeMax = Math.max(1, maxValue);
  const ratio = Math.min(1, Math.max(0, value / safeMax));
  const fillWidthPercent = Math.round(ratio * 100);
  const sourceEntries = Object.entries(sourceCounts)
    .filter(([, count]) => count > 0)
    .sort((left, right) => {
      if (right[1] !== left[1]) return right[1] - left[1];
      return left[0].localeCompare(right[0]);
    });
  const sourceTotal = sourceEntries.reduce((sum, [, count]) => sum + count, 0);
  if (!sourceEntries.length || sourceTotal <= 0) return null;
  const subtitle = sourceEntries
    .slice(0, 3)
    .map(([source, count]) => `${source}: ${count.toLocaleString("es-ES")}`)
    .join(" · ");

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-3">
        <div className="w-32 text-xs text-[color:var(--text-55)] truncate">{label}</div>
        <div className="flex-1 h-2 rounded-full bg-[color:var(--surface-70)] overflow-hidden border border-[color:var(--border-70)]">
          <div
            className="flex h-full overflow-hidden rounded-full"
            style={{ width: `${fillWidthPercent}%` }}
          >
            {sourceEntries.map(([source, count]) => (
              <div
                key={`${label}-${source}`}
                className="h-full"
                style={{
                  width: `${(count / sourceTotal) * 100}%`,
                  backgroundColor: pressSourceColorHex(source),
                }}
                title={`${source}: ${count.toLocaleString("es-ES")}`}
              />
            ))}
          </div>
        </div>
        <div className="w-12 text-right text-xs text-[color:var(--text-55)]">
          {value.toLocaleString("es-ES")}
        </div>
      </div>
      <div className="pl-[8.5rem] text-[10px] text-[color:var(--text-45)] truncate">{subtitle}</div>
    </div>
  );
}

function PressPublisherSourcesLegend({
  sourceTotals,
}: {
  sourceTotals: Record<string, number>;
}) {
  const entries = Object.entries(sourceTotals)
    .filter(([, count]) => count > 0)
    .sort((left, right) => {
      if (right[1] !== left[1]) return right[1] - left[1];
      return left[0].localeCompare(right[0]);
    })
    .slice(0, 8);
  if (!entries.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-[color:var(--text-55)]">
      <span className="uppercase tracking-[0.14em] text-[color:var(--text-45)]">Fuentes:</span>
      {entries.map(([source, count]) => (
        <span key={source} className="inline-flex items-center gap-1.5">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: pressSourceColorHex(source) }}
          />
          <span>
            {source} ({count.toLocaleString("es-ES")})
          </span>
        </span>
      ))}
    </div>
  );
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, idx) => (
        <div key={idx} className="flex items-center gap-3 animate-pulse">
          <div className="h-3 w-24 rounded-full bg-[color:var(--surface-70)] border border-[color:var(--border-60)]" />
          <div className="flex-1 h-2 rounded-full bg-[color:var(--surface-70)] border border-[color:var(--border-60)]" />
          <div className="h-3 w-8 rounded-full bg-[color:var(--surface-70)] border border-[color:var(--border-60)]" />
        </div>
      ))}
    </>
  );
}

type MentionSource = { name: string; url?: string };
type ManualOverride = ReputationItem["manual_override"];
type MentionGroup = {
  key: string;
  ids: string[];
  title: string;
  text?: string;
  geo?: string;
  actor?: string;
  author?: string;
  publisher?: string;
  sentiment?: string;
  rating?: number | null;
  rating_source?: string | null;
  published_at?: string | null;
  collected_at?: string | null;
  sources: MentionSource[];
  count: number;
  manual_override?: ManualOverride | null;
  reply_text?: string;
  reply_author?: string;
  replied_at?: string | null;
  reply_item_date?: string | null;
  author_item_date?: string | null;
};

function MentionCard({
  item,
  index,
  principalLabel,
  geoOptions,
  manualControlsEnabled = true,
  onOverride,
}: {
  item: MentionGroup;
  index: number;
  principalLabel: string;
  geoOptions: string[];
  manualControlsEnabled?: boolean;
  onOverride: (payload: OverridePayload) => Promise<void>;
}) {
  const sentimentTone = getSentimentTone(item.sentiment);
  const sanitizedTitle = cleanText(item.title) || "Sin título";
  const sanitizedText = cleanText(item.text);
  const displayDate = formatDate(item.published_at || item.collected_at);
  const [editOpen, setEditOpen] = useState(false);
  const [draftGeo, setDraftGeo] = useState(item.geo ?? "");
  const [draftSentiment, setDraftSentiment] = useState<SentimentValue>(
    (item.sentiment as SentimentValue) ?? "neutral",
  );
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const ratingValue = typeof item.rating === "number" ? item.rating : null;
  const ratingLabel = ratingValue !== null ? ratingValue.toFixed(1) : null;
  const blockedSources = item.sources.filter((src) => isManualOverrideBlockedSource(src));
  const ratingSourceKey = normalizeSourceKey(item.rating_source ?? "");
  const hasMarketSource = item.sources.some((source) =>
    MARKET_OPINION_SOURCE_KEYS.has(normalizeSourceKey(source.name)),
  );
  const hasPressSource = item.sources.some((source) => {
    const sourceName = (source.name || "").trim().toLowerCase();
    if (!sourceName) return false;
    if (PRESS_REPUTATION_SOURCE_SET.has(sourceName)) return true;
    const normalizedSourceName = normalizeSourceKey(sourceName);
    for (const candidate of PRESS_REPUTATION_SOURCE_SET) {
      if (normalizeSourceKey(candidate) === normalizedSourceName) {
        return true;
      }
    }
    return false;
  });
  const publisherLabel = hasPressSource
    ? cleanPublisherLabel(item.publisher || "")
    : "";
  const opinionAuthor = item.author || (hasMarketSource ? "Autor sin nombre" : null);
  const manualOverrideBlocked =
    !manualControlsEnabled ||
    blockedSources.length > 0 ||
    (ratingSourceKey && MANUAL_OVERRIDE_BLOCKED_SOURCES.has(ratingSourceKey));
  const blockedLabels = blockedSources.map((src) => {
    const key = normalizeSourceKey(src.name);
    return MANUAL_OVERRIDE_BLOCKED_LABELS[key] ?? src.name;
  });
  const primaryUrl = sanitizeExternalUrl(item.sources[0]?.url);
  if (!blockedLabels.length && ratingSourceKey) {
    blockedLabels.push(
      MANUAL_OVERRIDE_BLOCKED_LABELS[ratingSourceKey] ?? item.rating_source ?? "",
    );
  }

  useEffect(() => {
    setDraftGeo(item.geo ?? "");
    setDraftSentiment((item.sentiment as SentimentValue) ?? "neutral");
    setLocalError(null);
  }, [item.key, item.geo, item.sentiment]);

  const currentGeo = item.geo ?? "";
  const currentSentiment = (item.sentiment as SentimentValue) ?? "neutral";
  const geoChanged = draftGeo.trim() !== currentGeo;
  const sentimentChanged = draftSentiment !== currentSentiment;
  const isDirty = geoChanged || sentimentChanged;
  const manualUpdatedAt = item.manual_override?.updated_at ?? null;
  const geoListId = `geo-options-${index}`;

  const handleSave = async () => {
    if (!isDirty || saving) return;
    const trimmedGeo = draftGeo.trim();
    if (geoChanged && !trimmedGeo) {
      setLocalError("Indica un país válido para guardar el ajuste.");
      return;
    }
    if (!item.ids.length) {
      setLocalError("No hay IDs disponibles para aplicar el ajuste.");
      return;
    }

    const payload: OverridePayload = { ids: item.ids };
    if (geoChanged) payload.geo = trimmedGeo;
    if (sentimentChanged) payload.sentiment = draftSentiment;

    setSaving(true);
    setLocalError(null);
    try {
      await onOverride(payload);
      setEditOpen(false);
    } catch (error) {
      setLocalError(String(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <article
      className="group relative overflow-hidden rounded-[22px] border border-[color:var(--border-70)] bg-[color:var(--surface-85)] p-4 shadow-[var(--shadow-card)] animate-rise"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms` }}
    >
      <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-[color:var(--aqua)] via-[color:var(--blue)] to-transparent opacity-70" />
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-[color:var(--text-55)]">
        <span className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1">
          <MapPin className="h-3.5 w-3.5 text-[color:var(--blue)]" />
          {item.geo || "Global"}
        </span>
        <span className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1">
          <Building2 className="h-3.5 w-3.5 text-[color:var(--blue)]" />
          {item.actor || principalLabel}
        </span>
        {publisherLabel && (
          <span
            className="inline-flex max-w-[260px] items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1"
            title={publisherLabel}
          >
            <Newspaper className="h-3.5 w-3.5 text-[color:var(--blue)]" />
            <span className="truncate">{publisherLabel}</span>
          </span>
        )}
        {opinionAuthor && (
          <span
            className="inline-flex max-w-[250px] items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1"
            title={opinionAuthor}
          >
            <User className="h-3.5 w-3.5 text-[color:var(--blue)]" />
            <span className="truncate">{opinionAuthor}</span>
          </span>
        )}
        <span className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1">
          <Calendar className="h-3.5 w-3.5 text-[color:var(--blue)]" />
          {displayDate}
        </span>
        <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 ${sentimentTone.className}`}>
          {sentimentTone.icon}
          {sentimentTone.label}
        </span>
        {ratingValue !== null && (
          <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--aqua)]/40 [background-image:var(--gradient-chip)] px-2.5 py-1 text-[11px] text-[color:var(--brand-ink)] shadow-[var(--shadow-pill)]">
            <StarMeter rating={ratingValue} />
            <span className="font-semibold">{ratingLabel}</span>
            <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-45)]">/5</span>
          </span>
        )}
        {item.manual_override && (
          <span className="inline-flex items-center gap-1 rounded-full border border-[color:var(--aqua)]/40 bg-[color:var(--aqua)]/10 px-2.5 py-1 text-[11px] text-[color:var(--brand-ink)]">
            <Sparkles className="h-3 w-3" />
            Ajuste manual
          </span>
        )}
        {item.sources.length > 1 && (
          <span className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1 text-[11px] text-[color:var(--text-60)]">
            {item.sources.length} fuentes
          </span>
        )}
      </div>
      <div className="mt-3 text-base font-display font-semibold text-[color:var(--ink)]">
        {sanitizedTitle}
      </div>
      {sanitizedText && (
        <div
          className="mt-2 text-sm text-[color:var(--text-70)]"
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {sanitizedText}
        </div>
      )}
      {(item.reply_text || item.reply_author || item.replied_at) && (
        <div className="mt-3 rounded-2xl border border-[color:var(--aqua)]/35 bg-[color:var(--surface-80)] px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[color:var(--blue)]">
            CONTESTACION
          </div>
          {item.reply_author && (
            <div className="mt-1 text-[11px] text-[color:var(--text-55)]">
              {item.reply_author}
            </div>
          )}
          <div className="mt-1 text-xs text-[color:var(--ink)]">
            {cleanText(item.reply_text) || "Sin texto de respuesta"}
          </div>
        </div>
      )}
      {!manualOverrideBlocked && (
        <div className="mt-4 rounded-2xl border border-[color:var(--aqua)]/30 [background-image:var(--gradient-callout)] p-3 shadow-[inset_0_1px_0_var(--inset-highlight-strong)]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[10px] font-semibold uppercase tracking-[0.3em] text-[color:var(--blue)]">
              Control manual
            </div>
            <button
              onClick={() => setEditOpen((value) => !value)}
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--brand-ink)] shadow-[var(--shadow-pill)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pill-hover)]"
            >
              <PenSquare className="h-3.5 w-3.5" />
              {editOpen ? "Cerrar" : "Ajustar"}
            </button>
          </div>
          {!editOpen && (
            <div className="mt-2 text-xs text-[color:var(--text-55)]">
              {manualUpdatedAt
                ? `Último ajuste: ${formatDate(manualUpdatedAt)}`
                : "Ajusta país o sentimiento si el análisis no refleja tu criterio."}
            </div>
          )}
          {editOpen && (
            <div className="mt-3 grid gap-3">
              <div className="grid gap-1">
                <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-45)]">
                  País
                </span>
                <input
                  type="text"
                  list={geoListId}
                  value={draftGeo}
                  onChange={(e) => setDraftGeo(e.target.value)}
                  placeholder="Ej: España"
                  className="w-full rounded-2xl border border-[color:var(--border-70)] bg-[color:var(--surface-85)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight-strong)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
                />
                <datalist id={geoListId}>
                  {geoOptions.map((opt) => (
                    <option key={opt} value={opt} />
                  ))}
                </datalist>
              </div>
              <div className="grid gap-2">
                <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-45)]">
                  Sentimiento
                </span>
                <div className="flex flex-wrap gap-2">
                  {(["positive", "neutral", "negative"] as const).map((value) => {
                    const tone = getSentimentTone(value);
                    const active = value === draftSentiment;
                    return (
                      <button
                        key={value}
                        onClick={() => setDraftSentiment(value)}
                        className={
                          "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition " +
                          (active
                            ? `${tone.className} shadow-[var(--shadow-tone)]`
                            : "border-[color:var(--border-70)] bg-[color:var(--surface-80)] text-[color:var(--text-50)] hover:text-[color:var(--ink)]")
                        }
                      >
                        {tone.icon}
                        {tone.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              {localError && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                  {localError}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={handleSave}
                  disabled={!isDirty || saving}
                  className="inline-flex items-center gap-2 rounded-full bg-[color:var(--blue)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-white shadow-[0_12px_26px_rgba(0,68,129,0.28)] transition hover:-translate-y-0.5 hover:shadow-[0_16px_32px_rgba(0,68,129,0.32)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {saving ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  )}
                  Guardar ajuste
                </button>
                <button
                  onClick={() => {
                    setEditOpen(false);
                    setDraftGeo(currentGeo);
                    setDraftSentiment(currentSentiment);
                    setLocalError(null);
                  }}
                  className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--text-60)] transition hover:text-[color:var(--ink)]"
                >
                  <X className="h-3.5 w-3.5" />
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-[color:var(--text-45)]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-40)]">
            Fuentes
          </span>
          {item.sources.map((src) => {
            const safeUrl = sanitizeExternalUrl(src.url);
            return safeUrl ? (
              <a
                key={src.name}
                href={safeUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1 text-[11px] text-[color:var(--blue)] hover:text-[color:var(--brand-ink)] transition"
              >
                {src.name}
                <ArrowUpRight className="h-3 w-3" />
              </a>
            ) : (
              <span
                key={src.name}
                className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1 text-[11px] text-[color:var(--blue)]"
              >
                {src.name}
              </span>
            );
          })}
        </div>
        {primaryUrl && (
          <a
            href={primaryUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[color:var(--blue)] hover:text-[color:var(--brand-ink)] transition"
          >
            Ver detalle
            <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
    </article>
  );
}

function toDateInput(d: Date) {
  const iso = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
  return iso;
}

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function endOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

function shiftMonth(d: Date, step: number) {
  return new Date(d.getFullYear(), d.getMonth() + step, 1);
}

function isSameMonth(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
}

function formatMonthLabel(d: Date) {
  const value = new Intl.DateTimeFormat("es-ES", {
    month: "long",
    year: "numeric",
  }).format(d);
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function sanitizeExternalUrl(value?: string | null): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed, "https://example.com");
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return trimmed;
    }
  } catch {
    // ignore malformed urls
  }
  return null;
}

function unique(values: string[]) {
  return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b));
}

function toggleSource(
  source: string,
  sources: string[],
  setSources: (next: string[]) => void,
) {
  if (sources.includes(source)) {
    setSources(sources.filter((s) => s !== source));
  } else {
    setSources([...sources, source]);
  }
}

function normalizeKey(value: string) {
  return value
    .toLowerCase()
    .replace(/https?:\/\/(www\.)?/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function normalizeSourceKey(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function findDefaultGeoOption(options: string[]): string | null {
  for (const option of options) {
    const key = normalizeKey(option);
    if (key === "españa" || key === "espana" || key === "spain") {
      return option;
    }
  }
  return null;
}

type ActorStoreRatings = {
  appstore: MarketRating | null;
  google_play: MarketRating | null;
};

function buildActorStoreRatings(
  ratings: MarketRating[],
  actor: string,
  geo: string,
): ActorStoreRatings {
  const actorKey = normalizeKey(actor);
  const filtered = ratings.filter(
    (rating) => normalizeKey(rating.actor ?? "") === actorKey,
  );
  const appstore = pickMarketRating(filtered, geo, "appstore");
  const googlePlay = pickMarketRating(filtered, geo, "googleplay");
  return { appstore, google_play: googlePlay };
}

function pickMarketRating(
  ratings: MarketRating[],
  geo: string,
  sourceKey: string,
): MarketRating | null {
  if (!ratings.length) return null;
  const bySource = ratings.filter(
    (rating) => normalizeSourceKey(rating.source) === sourceKey,
  );
  const byGeo = filterRatingsByGeo(bySource, geo);
  return pickBestMarketRating(byGeo);
}

function filterRatingsByGeo(ratings: MarketRating[], geo: string) {
  if (!ratings.length) return ratings;
  const normalizedGeo = normalizeKey(geo);
  if (geo === "all") {
    const globals = ratings.filter((rating) => !rating.geo || normalizeKey(rating.geo) === "global");
    return globals.length ? globals : ratings;
  }
  const exact = ratings.filter(
    (rating) => normalizeKey(rating.geo ?? "") === normalizedGeo,
  );
  if (exact.length) return exact;
  const globals = ratings.filter((rating) => !rating.geo || normalizeKey(rating.geo) === "global");
  return globals.length ? globals : ratings;
}

function pickBestMarketRating(ratings: MarketRating[]) {
  if (!ratings.length) return null;
  return ratings.reduce<MarketRating | null>((best, current) => {
    if (!best) return current;
    const bestCount = best.rating_count ?? -1;
    const currentCount = current.rating_count ?? -1;
    if (currentCount > bestCount) return current;
    if (currentCount < bestCount) return best;
    const bestTime = best.collected_at ?? "";
    const currentTime = current.collected_at ?? "";
    return currentTime > bestTime ? current : best;
  }, null);
}

function getMarketRatingTrend(
  current: MarketRating | null,
  history: MarketRating[],
): { status: "up" | "down" | "flat" | "none"; previous: MarketRating | null } {
  if (!current) {
    return { status: "none", previous: null };
  }
  const previous = findPreviousMarketRating(current, history);
  if (!previous) {
    return { status: "none", previous: null };
  }
  const diff = current.rating - previous.rating;
  if (diff > 0.005) return { status: "up", previous };
  if (diff < -0.005) return { status: "down", previous };
  return { status: "flat", previous };
}

function findPreviousMarketRating(
  current: MarketRating,
  history: MarketRating[],
): MarketRating | null {
  if (!history.length) return null;
  const currentKey = marketRatingKey(current);
  const currentTime = marketRatingTimestamp(current.collected_at);
  const candidates = history
    .filter((entry) => marketRatingKey(entry) === currentKey)
    .sort(
      (a, b) => marketRatingTimestamp(b.collected_at) - marketRatingTimestamp(a.collected_at),
    );

  for (const entry of candidates) {
    const entryTime = marketRatingTimestamp(entry.collected_at);
    if (
      current.collected_at &&
      entry.collected_at &&
      entryTime === currentTime &&
      Math.abs(entry.rating - current.rating) < 0.0001
    ) {
      continue;
    }
    return entry;
  }
  return null;
}

function marketRatingKey(rating: MarketRating) {
  return [
    normalizeSourceKey(rating.source || ""),
    normalizeKey(rating.actor ?? ""),
    normalizeKey(rating.geo ?? ""),
    (rating.app_id ?? "").toLowerCase(),
    (rating.package_id ?? "").toLowerCase(),
  ].join("|");
}

function marketRatingTimestamp(value?: string | null) {
  if (!value) return 0;
  const ts = new Date(value).getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

function AppleMark({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path d="M16.365 1.43c0 1.13-.45 2.18-1.15 2.93-.73.79-1.92 1.4-3.04 1.31-.18-1.07.3-2.22 1.02-3.02.72-.8 1.95-1.39 3.17-1.22zM19.69 17.02c-.2.47-.43.91-.69 1.32-.35.56-.7 1.05-1.08 1.5-.52.6-1.08 1.17-1.78 1.19-.66.02-.88-.42-1.83-.42s-1.2.4-1.85.43c-.67.03-1.19-.57-1.7-1.17-1.43-1.67-2.52-4.7-1.05-6.76.72-1 1.87-1.62 3.15-1.64.62-.01 1.2.42 1.83.42.6 0 1.69-.52 2.86-.44.49.02 1.88.2 2.77 1.52-.07.05-1.66.97-1.64 2.9.02 2.3 2.03 3.07 2.05 3.08zM13.45 6.45c.6-.73 1.02-1.74.91-2.75-.87.04-1.92.58-2.55 1.31-.57.66-1.05 1.69-.92 2.68.98.08 1.96-.49 2.56-1.24z" />
    </svg>
  );
}

function AndroidMark({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 6L6.2 3.2" />
      <path d="M16 6l1.8-2.8" />
      <rect x="5" y="7" width="14" height="10" rx="2" />
      <circle cx="9" cy="12" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="15" cy="12" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  );
}

function isManualOverrideBlockedSource(source: MentionSource) {
  const key = normalizeSourceKey(source.name);
  if (MANUAL_OVERRIDE_BLOCKED_SOURCES.has(key)) return true;
  if (isAppleStoreUrl(source.url)) return true;
  return false;
}

function isAppleStoreUrl(url?: string) {
  if (!url) return false;
  try {
    const host = new URL(url).hostname.toLowerCase();
    return (
      host === "itunes.apple.com" ||
      host.endsWith(".itunes.apple.com") ||
      host === "apps.apple.com" ||
      host.endsWith(".apps.apple.com")
    );
  } catch {
    return false;
  }
}

function buildPrincipalAliases(actorPrincipal: ActorPrincipalMeta | null) {
  if (!actorPrincipal) return [];
  const values = [
    actorPrincipal.canonical,
    ...(actorPrincipal.names ?? []),
    ...(actorPrincipal.aliases ?? []),
  ];
  return Array.from(new Set(values.filter((v) => v && v.trim())));
}

function groupMentions(items: ReputationItem[]) {
  const map = new Map<string, MentionGroup>();

  for (const item of items) {
    const extractedActor = extractActor(item);
    const extractedAuthor = extractOpinionAuthor(item);
    const extractedPublisher = extractPublisherLabel(item);
    const title = cleanText(item.title || "");
    const text = cleanText(item.text || "");
    const reply = extractReply(item);
    const itemDate = item.published_at || item.collected_at || null;
    const base =
      title || text || item.url || String(item.id ?? "sin-titulo");
    const key = [
      normalizeKey(base),
      item.geo || "",
      extractedActor || "",
      extractedAuthor || "",
    ].join("|");

    if (!map.has(key)) {
      map.set(key, {
        key,
        ids: [],
        title: title || text || "Sin título",
        text: text || undefined,
        geo: item.geo || undefined,
        actor: extractedActor || undefined,
        author: extractedAuthor || undefined,
        publisher: extractedPublisher || undefined,
        sentiment: item.sentiment || undefined,
        rating: extractRating(item),
        rating_source: extractRatingSource(item),
        published_at: item.published_at || null,
        collected_at: item.collected_at || null,
        sources: [],
        count: 0,
        manual_override: item.manual_override ?? undefined,
        reply_text: reply?.text,
        reply_author: reply?.author,
        replied_at: reply?.replied_at ?? null,
        reply_item_date: reply ? itemDate : null,
        author_item_date: extractedAuthor ? itemDate : null,
      });
    }

    const group = map.get(key);
    if (!group) continue;

    group.count += 1;
    if (item.id && !group.ids.includes(item.id)) {
      group.ids.push(item.id);
    }

    if (reply) {
      const currentReplyItemDate = group.reply_item_date || "";
      const candidateReplyItemDate = itemDate || "";
      const shouldReplaceReply =
        !group.reply_text && !group.reply_author && !group.replied_at
          ? true
          : candidateReplyItemDate > currentReplyItemDate;
      if (shouldReplaceReply) {
        group.reply_text = reply.text;
        group.reply_author = reply.author;
        group.replied_at = reply.replied_at;
        group.reply_item_date = itemDate;
      }
    }

    const candidateDate = item.published_at || item.collected_at || "";
    const currentDate = group.published_at || group.collected_at || "";
    if (candidateDate && candidateDate > currentDate) {
      group.published_at = item.published_at || group.published_at;
      group.collected_at = item.collected_at || group.collected_at;
    }

    if (text && (!group.text || text.length > group.text.length)) {
      group.text = text;
    }

    if (!group.actor && extractedActor) {
      group.actor = extractedActor;
    }

    if (extractedAuthor) {
      const currentAuthorDate = group.author_item_date || "";
      const candidateAuthorDate = itemDate || "";
      if (!group.author || (candidateAuthorDate && candidateAuthorDate > currentAuthorDate)) {
        group.author = extractedAuthor;
        group.author_item_date = itemDate;
      }
    }

    if (extractedPublisher) {
      if (!group.publisher) {
        group.publisher = extractedPublisher;
      } else if (normalizeKey(group.publisher) !== normalizeKey(extractedPublisher)) {
        group.publisher = "Varios medios";
      }
    }

    if (item.manual_override) {
      const candidateOverrideAt = item.manual_override.updated_at ?? "";
      const currentOverrideAt = group.manual_override?.updated_at ?? "";
      if (!group.manual_override || candidateOverrideAt > currentOverrideAt) {
        group.manual_override = item.manual_override;
      }
    }

    const candidateRating = extractRating(item);
    if (candidateRating !== null && (group.rating === undefined || group.rating === null)) {
      group.rating = candidateRating;
      group.rating_source = extractRatingSource(item);
    }

    if (item.source) {
      const exists = group.sources.find((src) => src.name === item.source);
      if (!exists) {
        group.sources.push({ name: item.source, url: item.url || undefined });
      }
    }
  }

  return Array.from(map.values())
    .map((group) => ({
      ...group,
      sources: group.sources.sort((a, b) => a.name.localeCompare(b.name)),
    }))
    .sort((a, b) => {
      const da = a.published_at || a.collected_at || "";
      const db = b.published_at || b.collected_at || "";
      return db.localeCompare(da);
    });
}

function extractRating(item: ReputationItem) {
  const signals = (item.signals || {}) as Record<string, unknown>;
  const coerceStar = (raw: unknown): number | null => {
    if (raw === null || raw === undefined || typeof raw === "boolean") return null;
    let parsed: number | null = null;
    if (typeof raw === "number" && Number.isFinite(raw)) {
      parsed = raw;
    } else if (typeof raw === "string") {
      const compact = raw.trim().replace(",", ".");
      const direct = Number(compact);
      if (Number.isFinite(direct)) {
        parsed = direct;
      } else {
        const firstNumber = compact.match(/-?\d+(?:\.\d+)?/);
        if (firstNumber) {
          const asNumber = Number(firstNumber[0]);
          if (Number.isFinite(asNumber)) {
            parsed = asNumber;
          }
        }
      }
    }
    if (parsed === null || parsed <= 0) return null;
    return Math.max(0, Math.min(5, parsed));
  };
  const fromCandidate = (candidate: unknown, depth = 0): number | null => {
    if (depth > 3 || candidate === null || candidate === undefined) return null;
    const direct = coerceStar(candidate);
    if (direct !== null) return direct;
    if (Array.isArray(candidate)) {
      for (const entry of candidate) {
        const nested = fromCandidate(entry, depth + 1);
        if (nested !== null) return nested;
      }
      return null;
    }
    if (!candidate || typeof candidate !== "object") return null;
    const record = candidate as Record<string, unknown>;
    const nestedKeys = [
      "value",
      "rating",
      "score",
      "stars",
      "starRating",
      "star_rating",
      "user_rating",
      "userRating",
      "rating_value",
      "ratingValue",
      "reviewRating",
    ];
    for (const key of nestedKeys) {
      const nested = fromCandidate(record[key], depth + 1);
      if (nested !== null) return nested;
    }
    return null;
  };
  const candidates = [
    signals.rating,
    signals.score,
    signals.stars,
    signals.starRating,
    signals.star_rating,
    signals.userRating,
    signals.user_rating,
    signals.ratingValue,
    signals.rating_value,
    signals.reviewRating,
  ];
  for (const raw of candidates) {
    const value = fromCandidate(raw);
    if (value !== null) return value;
  }
  return null;
}

function extractActor(item: ReputationItem) {
  if (item.actor && item.actor.trim()) return item.actor;
  const signals = (item.signals || {}) as Record<string, unknown>;
  const raw = signals.actors;
  if (Array.isArray(raw)) {
    const first = raw.find((value) => typeof value === "string" && value.trim());
    if (typeof first === "string") return first;
  }
  return null;
}

function extractOpinionAuthor(item: ReputationItem) {
  const normalizeText = (value: unknown): string => {
    if (typeof value !== "string") return "";
    return value.replace(/\s+/g, " ").trim();
  };
  const fromValue = (value: unknown): string => {
    const direct = normalizeText(value);
    if (direct) return direct;
    if (!value || typeof value !== "object") return "";
    if (Array.isArray(value)) {
      for (const entry of value) {
        const nested = fromValue(entry);
        if (nested) return nested;
      }
      return "";
    }
    const record = value as Record<string, unknown>;
    const keys = [
      "author",
      "author_name",
      "authorName",
      "user_name",
      "userName",
      "username",
      "reviewer_name",
      "reviewerName",
      "nickname",
      "nickName",
      "name",
      "display_name",
      "displayName",
    ];
    for (const key of keys) {
      const nested = fromValue(record[key]);
      if (nested) return nested;
    }
    return "";
  };

  const direct = normalizeText(item.author);
  if (direct) return direct;
  const signals = (item.signals || {}) as Record<string, unknown>;
  const signalKeys = [
    "author",
    "author_name",
    "authorName",
    "user_name",
    "userName",
    "username",
    "reviewer_name",
    "reviewerName",
    "nickname",
    "nickName",
  ];
  for (const key of signalKeys) {
    const candidate = fromValue(signals[key]);
    if (candidate) return candidate;
  }
  return null;
}

function extractReply(item: ReputationItem): {
  text: string;
  author?: string;
  replied_at?: string | null;
} | null {
  const signals = (item.signals || {}) as Record<string, unknown>;
  const textKeys = [
    "reply_text",
    "response_text",
    "developer_reply",
    "developer_response",
    "owner_response",
    "business_response",
    "response",
    "reply",
  ];
  const authorKeys = [
    "reply_author",
    "response_author",
    "developer_name",
    "owner_name",
    "author",
  ];
  const dateKeys = [
    "reply_at",
    "response_at",
    "replied_at",
    "developer_response_at",
    "owner_response_at",
    "date",
    "time",
    "published_at",
    "updated_at",
  ];
  const containerKeys = [
    "reply",
    "response",
    "developer_reply",
    "developer_response",
    "owner_response",
    "business_response",
  ];

  const normalizeText = (value: unknown): string => {
    if (typeof value !== "string") return "";
    return value.replace(/\s+/g, " ").trim();
  };

  const extractText = (value: unknown): string => {
    const direct = normalizeText(value);
    if (direct) return direct;
    if (!value || typeof value !== "object") return "";
    const record = value as Record<string, unknown>;
    for (const key of ["text", "content", "body", "message", "reply", "response", "value"]) {
      const candidate = normalizeText(record[key]);
      if (candidate) return candidate;
    }
    return "";
  };

  const extractAuthor = (value: unknown): string => {
    const direct = normalizeText(value);
    if (direct) return direct;
    if (!value || typeof value !== "object") return "";
    const record = value as Record<string, unknown>;
    for (const key of ["author", "name", "display_name", "developer", "owner"]) {
      const candidate = normalizeText(record[key]);
      if (candidate) return candidate;
    }
    return "";
  };

  const extractDate = (value: unknown): string | null => {
    if (typeof value === "string") {
      const raw = value.trim();
      if (raw) return raw;
      return null;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? null : date.toISOString();
    }
    if (!value || typeof value !== "object") return null;
    const record = value as Record<string, unknown>;
    for (const key of dateKeys) {
      const candidate = extractDate(record[key]);
      if (candidate) return candidate;
    }
    return null;
  };

  let replyText = "";
  let replyAuthor = "";
  let repliedAt: string | null = null;

  for (const key of textKeys) {
    replyText = extractText(signals[key]);
    if (replyText) break;
  }

  for (const key of containerKeys) {
    const container = signals[key];
    if (!container || typeof container !== "object") continue;
    if (!replyText) {
      replyText = extractText(container);
    }
    if (!replyAuthor) {
      replyAuthor = extractAuthor(container);
    }
    if (!repliedAt) {
      repliedAt = extractDate(container);
    }
  }

  if (!replyAuthor) {
    for (const key of authorKeys) {
      replyAuthor = extractAuthor(signals[key]);
      if (replyAuthor) break;
    }
  }

  if (!repliedAt) {
    for (const key of dateKeys) {
      repliedAt = extractDate(signals[key]);
      if (repliedAt) break;
    }
  }

  const hasReplyFlag = Boolean(signals.has_reply);
  if (!replyText && !replyAuthor && !repliedAt && !hasReplyFlag) {
    return null;
  }

  return {
    text: replyText,
    author: replyAuthor || undefined,
    replied_at: repliedAt,
  };
}

function extractRatingSource(item: ReputationItem) {
  if (!item.source) return null;
  return item.source;
}

function StarMeter({ rating }: { rating: number }) {
  const safe = Math.max(0, Math.min(5, rating));
  const width = `${(safe / 5) * 100}%`;
  return (
    <span className="relative inline-flex items-center">
      <span className="flex items-center text-[color:var(--brand-ink)]/25">
        {Array.from({ length: 5 }).map((_, idx) => (
          <Star key={`empty-${idx}`} className="h-3.5 w-3.5" />
        ))}
      </span>
      <span
        className="absolute left-0 top-0 flex h-full items-center overflow-hidden text-[color:var(--aqua)]"
        style={{ width }}
      >
        {Array.from({ length: 5 }).map((_, idx) => (
          <Star key={`fill-${idx}`} className="h-3.5 w-3.5 fill-current" />
        ))}
      </span>
    </span>
  );
}

function isPrincipalName(name: string, principalAliases: string[]) {
  if (!name) return false;
  const key = normalizeKey(name);
  if (!key) return false;
  return principalAliases.includes(key);
}

function containsPrincipal(text: string, principalAliases: string[]) {
  if (!text) return false;
  const haystack = normalizeKey(text);
  if (!haystack) return false;
  return principalAliases.some((alias) => alias && haystack.includes(alias));
}

function isPrincipalItem(item: ReputationItem, principalAliases: string[]) {
  if (item.actor) return isPrincipalName(item.actor, principalAliases);
  const haystack = `${item.title ?? ""} ${item.text ?? ""}`;
  return containsPrincipal(haystack, principalAliases);
}

function isPrincipalGroup(item: MentionGroup, principalAliases: string[]) {
  if (item.actor) return isPrincipalName(item.actor, principalAliases);
  const haystack = `${item.title ?? ""} ${item.text ?? ""}`;
  return containsPrincipal(haystack, principalAliases);
}

function buildEntityLabel(base: string, geo: string) {
  return geo === "all" ? `${base} (global)` : `${base} ${geo}`;
}

function cleanText(value?: string | null) {
  if (!value) return "";
  if (typeof window === "undefined") {
    return value.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  }
  const doc = new DOMParser().parseFromString(value, "text/html");
  return (doc.body.textContent || "").replace(/\s+/g, " ").trim();
}

type AnsweredMentionTotals = {
  opinionsTotal: number;
  opinionsPositive: number;
  opinionsNeutral: number;
  opinionsNegative: number;
  answeredTotal: number;
  answeredPositive: number;
  answeredNeutral: number;
  answeredNegative: number;
  answeredRatio: number;
};

function toAnsweredMentionTotals(
  totals: ResponseSummaryTotals | null | undefined,
): AnsweredMentionTotals | null {
  if (!totals) return null;
  const opinionsPositive =
    Number(totals.answered_positive || 0) + Number(totals.unanswered_positive || 0);
  const opinionsNeutral =
    Number(totals.answered_neutral || 0) + Number(totals.unanswered_neutral || 0);
  const opinionsNegative =
    Number(totals.answered_negative || 0) + Number(totals.unanswered_negative || 0);
  const opinionsTotal = Number(totals.opinions_total || 0);
  const answeredTotal = Number(totals.answered_total || 0);
  return {
    opinionsTotal,
    opinionsPositive,
    opinionsNeutral,
    opinionsNegative,
    answeredTotal,
    answeredPositive: Number(totals.answered_positive || 0),
    answeredNeutral: Number(totals.answered_neutral || 0),
    answeredNegative: Number(totals.answered_negative || 0),
    answeredRatio: opinionsTotal > 0 ? answeredTotal / opinionsTotal : 0,
  };
}

function summarizeAnsweredMentions(items: MentionGroup[]): AnsweredMentionTotals {
  const totals: AnsweredMentionTotals = {
    opinionsTotal: items.length,
    opinionsPositive: 0,
    opinionsNeutral: 0,
    opinionsNegative: 0,
    answeredTotal: 0,
    answeredPositive: 0,
    answeredNeutral: 0,
    answeredNegative: 0,
    answeredRatio: 0,
  };
  for (const item of items) {
    if (item.sentiment === "positive") totals.opinionsPositive += 1;
    if (item.sentiment === "neutral") totals.opinionsNeutral += 1;
    if (item.sentiment === "negative") totals.opinionsNegative += 1;
    const isAnswered = Boolean(item.reply_text || item.reply_author || item.replied_at);
    if (!isAnswered) continue;
    totals.answeredTotal += 1;
    if (item.sentiment === "positive") totals.answeredPositive += 1;
    if (item.sentiment === "neutral") totals.answeredNeutral += 1;
    if (item.sentiment === "negative") totals.answeredNegative += 1;
  }
  totals.answeredRatio = totals.opinionsTotal
    ? totals.answeredTotal / totals.opinionsTotal
    : 0;
  return totals;
}

function formatResponseCoverageFromMentions(
  totals: AnsweredMentionTotals,
  options?: { includeTotals?: boolean },
): string {
  const percent = `${(totals.answeredRatio * 100).toFixed(1)}%`;
  if (options?.includeTotals === false) return percent;
  return `${percent} (${totals.answeredTotal}/${totals.opinionsTotal})`;
}

function formatDate(value?: string | null, withTime = true) {
  if (!value) return "Sin fecha";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: withTime ? "short" : undefined,
  }).format(d);
}

function buildRangeLabel(fromDate?: string, toDate?: string) {
  const fromLabel = fromDate
    ? formatDate(`${fromDate}T00:00:00`, false)
    : "Inicio";
  const toLabel = toDate ? formatDate(`${toDate}T23:59:59`, false) : "Hoy";
  return `${fromLabel} → ${toLabel}`;
}

function buildMentionsPeriodLabel(fromDate?: string, toDate?: string) {
  const fromLabel = formatDateInputLabel(fromDate || null);
  const toLabel = formatDateInputLabel(toDate || null);
  if (fromLabel === "Todos" && toLabel === "Todos") return "periodo seleccionado";
  if (fromLabel === "Todos") return `hasta ${toLabel}`;
  if (toLabel === "Todos") return `desde ${fromLabel}`;
  return `${fromLabel} al ${toLabel}`;
}

function formatDateInputLabel(value?: string | null) {
  if (!value) return "Todos";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return value;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

function formatSentimentFilterLabel(value: SentimentFilter) {
  if (value === "all") return "Todos";
  if (value === "positive") return "Positivo";
  if (value === "negative") return "Negativo";
  return "Neutral";
}

function formatRatioPercent(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "0.0%";
  return `${(value * 100).toFixed(1)}%`;
}

function marketAlertTone(severity: string) {
  const normalized = (severity || "").toLowerCase();
  if (normalized === "critical") return "text-rose-300 border-rose-400/40 bg-rose-500/10";
  if (normalized === "high") return "text-amber-300 border-amber-400/40 bg-amber-500/10";
  if (normalized === "medium") return "text-sky-300 border-sky-400/40 bg-sky-500/10";
  return "text-emerald-300 border-emerald-400/40 bg-emerald-500/10";
}

function getLatestDate(items: ReputationItem[]) {
  let latest = "";
  for (const item of items) {
    const candidate = item.published_at || item.collected_at || "";
    if (candidate && candidate > latest) {
      latest = candidate;
    }
  }
  return latest || null;
}

function getSentimentTone(sentiment?: string | null) {
  if (sentiment === "positive") {
    return {
      label: "Positivo",
      className: "bg-emerald-50 text-emerald-700 border-emerald-200",
      icon: <ThumbsUp className="h-3.5 w-3.5" />,
    };
  }
  if (sentiment === "negative") {
    return {
      label: "Negativo",
      className: "bg-rose-50 text-rose-700 border-rose-200",
      icon: <ThumbsDown className="h-3.5 w-3.5" />,
    };
  }
  return {
    label: "Neutral",
    className: "bg-slate-50 text-slate-600 border-slate-200",
    icon: <Minus className="h-3.5 w-3.5" />,
  };
}

function summarize(items: ReputationItem[]) {
  let positive = 0;
  let neutral = 0;
  let negative = 0;
  let totalScore = 0;
  let scored = 0;

  for (const item of items) {
    if (item.sentiment === "positive") positive += 1;
    if (item.sentiment === "neutral") neutral += 1;
    if (item.sentiment === "negative") negative += 1;
    const score = Number((item.signals as Record<string, unknown>)?.sentiment_score);
    if (!Number.isNaN(score)) {
      totalScore += score;
      scored += 1;
    }
  }

  return {
    positive,
    neutral,
    negative,
    avgScore: scored ? totalScore / scored : 0,
  };
}

function formatVsValue(
  principal: ReactNode,
  comparison?: ReactNode | null,
  options?: { containerClassName?: string; vsClassName?: string },
): ReactNode {
  if (!comparison) return principal;
  const containerClassName =
    options?.containerClassName ?? "inline-flex items-center justify-center whitespace-nowrap";
  const vsClassName =
    options?.vsClassName ??
    "mx-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-45)]";
  return (
    <span className={containerClassName}>
      <span>{principal}</span>
      <span className={vsClassName}>vs</span>
      <span>{comparison}</span>
    </span>
  );
}

function createMarketActorSourceCounts(): MarketActorSourceCounts {
  return {
    appstore: 0,
    google_play: 0,
  };
}

function normalizeMarketActorSourceKey(source?: string | null): MarketActorSourceKey | null {
  const normalizedSource = normalizeSourceKey(source ?? "");
  if (normalizedSource === "appstore") return "appstore";
  if (normalizedSource === "googleplay") return "google_play";
  return null;
}

function countMarketSourceTotals(items: ReputationItem[]): MarketActorSourceCounts {
  const totals = createMarketActorSourceCounts();
  for (const item of items) {
    const sourceKey = normalizeMarketActorSourceKey(item.source);
    if (!sourceKey) continue;
    totals[sourceKey] += 1;
  }
  return totals;
}

function buildMarketActorRows(items: ReputationItem[]): MarketActorRow[] {
  const map = new Map<string, MarketActorRow>();
  for (const item of items) {
    const actorLabel = item.actor?.trim() || "Sin actor";
    const sourceKey = normalizeMarketActorSourceKey(item.source);
    if (!sourceKey) continue;
    const actorKey = normalizeKey(actorLabel) || actorLabel.toLowerCase();
    if (!map.has(actorKey)) {
      map.set(actorKey, {
        key: actorKey,
        label: actorLabel,
        count: 0,
        sourceCounts: createMarketActorSourceCounts(),
      });
    }
    const row = map.get(actorKey);
    if (!row) continue;
    row.count += 1;
    row.sourceCounts[sourceKey] += 1;
  }
  return Array.from(map.values()).sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.label.localeCompare(b.label);
  });
}

function formatPressSourceLabel(source?: string | null): string {
  const normalized = normalizeSourceKey(source ?? "");
  if (!normalized) return "Desconocida";
  return PRESS_SOURCE_LABELS[normalized] ?? source?.trim() ?? normalized;
}

function pressSourceColorHex(sourceLabel: string): string {
  const key = normalizeKey(sourceLabel || "Desconocida");
  const fixed = PRESS_SOURCE_COLOR_BY_LABEL[key];
  if (fixed) return fixed;
  const hash = sourceLabel
    .split("")
    .reduce((sum, char, idx) => sum + char.charCodeAt(0) * (idx + 1), 0);
  return PRESS_SOURCE_COLOR_FALLBACK[Math.abs(hash) % PRESS_SOURCE_COLOR_FALLBACK.length];
}

function normalizePublisherDomain(value?: string | null): string {
  if (!value) return "";
  const trimmed = value.trim();
  if (!trimmed) return "";
  try {
    const parsed = new URL(trimmed);
    return parsed.hostname.replace(/^www\./i, "").toLowerCase();
  } catch {
    const cleaned = trimmed
      .replace(/^https?:\/\//i, "")
      .replace(/^www\./i, "")
      .split(/[/?#]/)[0]
      .toLowerCase();
    return cleaned.includes(".") ? cleaned : "";
  }
}

function isGoogleAggregatorDomain(domain: string): boolean {
  if (!domain) return false;
  return (
    domain === "news.google.com" ||
    domain.endsWith(".news.google.com") ||
    domain === "news.googleusercontent.com" ||
    domain.endsWith(".googleusercontent.com")
  );
}

function cleanPublisherLabel(value?: string | null): string {
  const cleaned = cleanText(value || "").trim().replace(/\s+/g, " ");
  return cleaned.replace(/^[\s\-–—|,;:.]+|[\s\-–—|,;:.]+$/g, "");
}

function extractPublisherFromTitle(title?: string | null): string {
  const cleanedTitle = cleanPublisherLabel(title);
  if (!cleanedTitle) return "";
  const parts = cleanedTitle.split(/\s(?:-|–|—|\|)\s/);
  if (parts.length < 2) return "";
  return cleanPublisherLabel(parts[parts.length - 1]);
}

function extractPublisherFromHtmlSnippet(text?: string | null): string {
  if (!text) return "";
  const fontMatch = /<font[^>]*>([\s\S]*?)<\/font>/i.exec(text);
  if (fontMatch?.[1]) {
    return cleanPublisherLabel(fontMatch[1]);
  }
  return "";
}

function extractPublisherLabel(item: ReputationItem): string | null {
  const signals = (item.signals || {}) as Record<string, unknown>;
  const signalPublisherName = cleanPublisherLabel(String(signals.publisher_name || ""));
  if (signalPublisherName && normalizeKey(signalPublisherName) !== "google news") {
    return signalPublisherName;
  }

  const signalSource = cleanPublisherLabel(String(signals.source || ""));
  if (signalSource && normalizeKey(signalSource) !== "google news") {
    return signalSource;
  }

  const titlePublisher = cleanPublisherLabel(extractPublisherFromTitle(item.title));
  if (titlePublisher && normalizeKey(titlePublisher) !== "google news") {
    return titlePublisher;
  }

  const htmlPublisher = cleanPublisherLabel(extractPublisherFromHtmlSnippet(item.text));
  if (htmlPublisher && normalizeKey(htmlPublisher) !== "google news") {
    return htmlPublisher;
  }

  const signalDomain = normalizePublisherDomain(String(signals.publisher_domain || ""));
  if (signalDomain && !isGoogleAggregatorDomain(signalDomain)) {
    return signalDomain;
  }

  const urlDomain = normalizePublisherDomain(item.url);
  if (urlDomain && !isGoogleAggregatorDomain(urlDomain)) {
    return urlDomain;
  }
  return null;
}

function countPressPublisherSourceTotals(items: ReputationItem[]): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const item of items) {
    const sourceLabel = formatPressSourceLabel(item.source);
    totals[sourceLabel] = (totals[sourceLabel] || 0) + 1;
  }
  return totals;
}

function buildPressPublisherRows(items: ReputationItem[]): PressPublisherRow[] {
  const map = new Map<string, PressPublisherRow>();
  for (const item of items) {
    const sourceLabel = formatPressSourceLabel(item.source);
    const publisherLabel = extractPublisherLabel(item) || "Medio no identificado";
    const key = normalizeKey(publisherLabel) || publisherLabel.toLowerCase();
    if (!map.has(key)) {
      map.set(key, {
        key,
        label: publisherLabel,
        count: 0,
        sourceCounts: {},
      });
    }
    const row = map.get(key);
    if (!row) continue;
    row.count += 1;
    row.sourceCounts[sourceLabel] = (row.sourceCounts[sourceLabel] || 0) + 1;
  }
  return Array.from(map.values()).sort((left, right) => {
    if (right.count !== left.count) return right.count - left.count;
    return left.label.localeCompare(right.label);
  });
}

function buildComparativeSeries(
  items: ReputationItem[],
  selectedActor: string,
  principalAliases: string[],
  fromDate?: string,
  toDate?: string,
) {
  const restrictActor =
    selectedActor !== "all" && !isPrincipalName(selectedActor, principalAliases);
  const normalizedActor = selectedActor.toLowerCase();
  const map = new Map<
    string,
    {
      principalScore: number;
      principalCount: number;
      actorScore: number;
      actorCount: number;
    }
  >();

  for (const item of items) {
    const rawDate = item.published_at || item.collected_at;
    if (!rawDate) continue;
    const date = rawDate.slice(0, 10);
    const score = Number(
      (item.signals as Record<string, unknown>)?.sentiment_score,
    );
    if (Number.isNaN(score)) continue;

    if (!map.has(date)) {
      map.set(date, {
        principalScore: 0,
        principalCount: 0,
        actorScore: 0,
        actorCount: 0,
      });
    }
    const entry = map.get(date);
    if (!entry) continue;

    if (isPrincipalItem(item, principalAliases)) {
      entry.principalScore += score;
      entry.principalCount += 1;
      continue;
    }

    if (item.actor) {
      const name = item.actor.toLowerCase();
      if (!restrictActor || name === normalizedActor) {
        entry.actorScore += score;
        entry.actorCount += 1;
      }
    }
  }

  const daily = Array.from(map.entries())
    .map(([date, entry]) => ({
      date,
      principal: entry.principalCount
        ? entry.principalScore / entry.principalCount
        : null,
      actor: entry.actorCount ? entry.actorScore / entry.actorCount : null,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  if (!daily.length) return [];

  const start = fromDate || daily[0].date;
  const end = toDate || daily[daily.length - 1].date;
  const dailyMap = new Map(daily.map((row) => [row.date, row]));

  let principalAcc = 0;
  let actorAcc = 0;
  const result: { date: string; principal: number; actor: number }[] = [];

  const cursor = new Date(`${start}T00:00:00`);
  const endDate = new Date(`${end}T00:00:00`);

  while (cursor <= endDate) {
    const key = toDateInput(cursor);
    const row = dailyMap.get(key);
    if (row) {
      if (typeof row.principal === "number") {
        principalAcc += row.principal;
      }
      if (typeof row.actor === "number") {
        actorAcc += row.actor;
      }
    }
    result.push({
      date: key,
      principal: principalAcc,
      actor: actorAcc,
    });
    cursor.setDate(cursor.getDate() + 1);
  }

  return result;
}

function downloadChartCsv(
  data: { date: string; principal: number | null; actor: number | null }[],
  principalLabel: string,
  actorLabel: string,
  filename: string,
  includeActor = true,
) {
  const headers = includeActor
    ? ["Fecha", principalLabel, actorLabel]
    : ["Fecha", principalLabel];
  const rows = data.map((row) =>
    includeActor
      ? [
          row.date,
          typeof row.principal === "number" ? row.principal.toFixed(3) : "",
          typeof row.actor === "number" ? row.actor.toFixed(3) : "",
        ]
      : [row.date, typeof row.principal === "number" ? row.principal.toFixed(3) : ""],
  );
  downloadCsv(filename, headers, rows);
}

const MENTIONS_HEADERS = [
  "ids",
  "titulo",
  "texto",
  "pais",
  "actor",
  "autor",
  "sentimiento",
  "rating",
  "fecha_publicada",
  "fecha_recolectada",
  "fuentes",
  "conteo",
  "ajuste_manual",
];

function buildMentionsRows(items: MentionGroup[]) {
  return items.map((item) => [
    item.ids.join("|"),
    item.title,
    item.text ?? "",
    item.geo ?? "",
    item.actor ?? "",
    item.author ?? "",
    item.sentiment ?? "",
    item.rating ?? "",
    item.published_at ?? "",
    item.collected_at ?? "",
    item.sources.map((s) => s.name).join("|"),
    item.count,
    item.manual_override ? "si" : "",
  ]);
}

function buildDownloadName(prefix: string, fromDate?: string, toDate?: string) {
  const safePrefix = prefix.replace(/[^a-zA-Z0-9_-]+/g, "_");
  const rangeFrom = fromDate || "inicio";
  const rangeTo = toDate || "hoy";
  return `${safePrefix}_${rangeFrom}_${rangeTo}`;
}

function downloadMentionsWorkbook({
  principalItems,
  actorItems,
  principalLabel,
  actorLabel,
  filename,
  activeTab,
  includeActorSheet = true,
}: {
  principalItems: MentionGroup[];
  actorItems: MentionGroup[];
  principalLabel: string;
  actorLabel: string;
  filename: string;
  activeTab: "principal" | "actor";
  includeActorSheet?: boolean;
}) {
  const principalName = sanitizeSheetName(principalLabel || "Principal", "Principal");
  let actorName = sanitizeSheetName(actorLabel || "Actor", "Actor");
  if (actorName === principalName) {
    const suffix = " (2)";
    actorName = `${actorName.slice(0, Math.max(0, 31 - suffix.length))}${suffix}`;
  }

  const principalSheet = {
    name: principalName,
    headers: MENTIONS_HEADERS,
    rows: buildMentionsRows(principalItems),
  };
  const actorSheet = {
    name: actorName,
    headers: MENTIONS_HEADERS,
    rows: buildMentionsRows(actorItems),
  };
  const sheets = includeActorSheet
    ? activeTab === "actor"
      ? [actorSheet, principalSheet]
      : [principalSheet, actorSheet]
    : [principalSheet];

  const workbook = buildWorkbookXml(sheets);
  downloadWorkbook(filename, workbook);
}

function downloadCsv(
  filename: string,
  headers: string[],
  rows: (string | number | null | undefined)[][],
) {
  const csvRows = [headers, ...rows].map((row) =>
    row.map((cell) => escapeCsvCell(cell)).join(","),
  );
  const content = `\uFEFF${csvRows.join("\n")}`;
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function escapeCsvCell(value: string | number | null | undefined) {
  if (value === null || value === undefined) return "";
  const str = String(value);
  if (/["\n,]/.test(str)) {
    return `"${str.replace(/"/g, "\"\"")}"`;
  }
  return str;
}

function downloadWorkbook(filename: string, xml: string) {
  const blob = new Blob([xml], { type: "application/vnd.ms-excel" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".xls") ? filename : `${filename}.xls`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function sanitizeSheetName(value: string, fallback: string) {
  const cleaned = value.replace(/[\\/?*\\[\\]:]/g, " ").replace(/\s+/g, " ").trim();
  const name = cleaned || fallback;
  return name.slice(0, 31);
}

function buildWorkbookXml(
  sheets: {
    name: string;
    headers: string[];
    rows: (string | number | null | undefined)[][];
  }[],
) {
  const xmlSheets = sheets
    .map((sheet) => buildWorksheetXml(sheet.name, sheet.headers, sheet.rows))
    .join("");

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<?mso-application progid="Excel.Sheet"?>',
    '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
    ' xmlns:o="urn:schemas-microsoft-com:office:office"',
    ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
    ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"',
    ' xmlns:html="http://www.w3.org/TR/REC-html40">',
    xmlSheets,
    "</Workbook>",
  ].join("");
}

function buildWorksheetXml(
  name: string,
  headers: string[],
  rows: (string | number | null | undefined)[][],
) {
  const allRows = [headers, ...rows];
  const rowsXml = allRows
    .map(
      (row) =>
        `<Row>${row.map((cell) => buildCellXml(cell)).join("")}</Row>`,
    )
    .join("");
  return `<Worksheet ss:Name="${escapeXml(name)}"><Table>${rowsXml}</Table></Worksheet>`;
}

function buildCellXml(value: string | number | null | undefined) {
  if (value === null || value === undefined) {
    return '<Cell><Data ss:Type="String"></Data></Cell>';
  }
  const type =
    typeof value === "number" && Number.isFinite(value) ? "Number" : "String";
  return `<Cell><Data ss:Type="${type}">${escapeXml(String(value))}</Data></Cell>`;
}

function escapeXml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
