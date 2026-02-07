"use client";

/**
 * Vista de sentimiento historico por pais / periodo / fuente.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import dynamic from "next/dynamic";
import {
  ArrowUpRight,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  Loader2,
  MapPin,
  MessageSquare,
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
import type {
  ActorPrincipalMeta,
  MarketRating,
  IngestJob,
  ReputationCacheDocument,
  ReputationItem,
  ReputationMeta,
} from "@/lib/types";

const SENTIMENTS = ["all", "positive", "neutral", "negative"] as const;
const MANUAL_OVERRIDE_BLOCKED_SOURCES = new Set(["appstore", "googlereviews"]);
const MANUAL_OVERRIDE_BLOCKED_LABELS: Record<string, string> = {
  appstore: "App Store",
  googlereviews: "Google Reviews",
};
const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

type SentimentFilter = (typeof SENTIMENTS)[number];
type SentimentValue = Exclude<SentimentFilter, "all">;
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

type SentimentViewProps = {
  mode?: DashboardMode;
};

const SentimentChart = dynamic(
  () => import("@/components/SentimentCharts").then((mod) => mod.SentimentChart),
  { ssr: false }
);
const DashboardChart = dynamic(
  () => import("@/components/SentimentCharts").then((mod) => mod.DashboardChart),
  { ssr: false }
);

type DashboardMention = {
  key: string;
  kind: "sentiment";
  title: string;
  text?: string;
  geo?: string;
  actor?: string;
  sentiment?: string | null;
  rating?: number | null;
  date?: string | null;
  sources?: string[];
};

export function SentimentView({ mode = "sentiment" }: SentimentViewProps) {
  const today = useMemo(() => new Date(), []);
  const defaultTo = useMemo(() => toDateInput(today), [today]);
  const defaultFrom = useMemo(() => {
    const d = new Date(today);
    d.setFullYear(d.getFullYear() - 2);
    return toDateInput(d);
  }, [today]);
  const DASHBOARD_DAYS = 30;
  const dashboardTo = useMemo(() => toDateInput(today), [today]);
  const dashboardFrom = useMemo(() => {
    const d = new Date(today);
    d.setDate(d.getDate() - (DASHBOARD_DAYS - 1));
    return toDateInput(d);
  }, [today]);

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
  const isDashboard = mode === "dashboard";
  const effectiveSentiment = isDashboard ? "all" : sentiment;
  const effectiveActor = isDashboard ? "all" : actor;
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
  const reputationCacheMissing = meta?.cache_available === false;
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

  useEffect(() => {
    if (!isDashboard) return;
    if (sentiment !== "all") setSentiment("all");
    if (actor !== "all") setActor("all");
  }, [isDashboard, sentiment, actor]);

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
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<IngestSuccessDetail>).detail;
      if (!detail) return;
      if (detail.kind === "reputation") {
        setReputationRefresh((value) => value + 1);
      }
    };
    window.addEventListener(INGEST_SUCCESS_EVENT, handler as EventListener);
    return () => {
      window.removeEventListener(INGEST_SUCCESS_EVENT, handler as EventListener);
    };
  }, [reputationRefresh]);

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
  }, [profileRefresh]);

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

  useEffect(() => {
    let alive = true;
    apiGetCached<ReputationMeta>("/reputation/meta", { ttlMs: 60000 })
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
  }, [profileRefresh]);

  useEffect(() => {
    let alive = true;

    // If comparing actor principal vs another actor, request both datasets and combine them.
    const fetchCombinedIfComparing = async () => {
      setItemsLoading(true);
      if (effectiveActor !== "all" && !isPrincipalName(effectiveActor, principalAliasKeys)) {
        const makeFilter = (overrides: Partial<Record<string, unknown>>) => {
          const f: Record<string, unknown> = {};
          if (effectiveFromDate) f.from_date = effectiveFromDate;
          if (effectiveToDate) f.to_date = effectiveToDate;
          if (effectiveSentiment !== "all") f.sentiment = effectiveSentiment;
          if (geo !== "all") f.geo = geo;
          if (sources.length) f.sources = sources.join(",");
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
      if (sources.length) params.set("sources", sources.join(","));

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
    entityParam,
    geo,
    effectiveActor,
    sources,
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
    if (sources.length) params.set("sources", sources.join(","));

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
    sources,
    overrideRefresh,
    reputationRefresh,
  ]);

  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of items) {
      if (!item.source) continue;
      counts[item.source] = (counts[item.source] || 0) + 1;
    }
    return counts;
  }, [items]);
  const sourcesOptions = useMemo(() => {
    const fromCounts = Object.keys(sourceCounts);
    if (fromCounts.length) {
      return fromCounts.sort((a, b) => a.localeCompare(b));
    }
    const fromMeta = meta?.sources_available ?? meta?.sources_enabled ?? [];
    return fromMeta.filter(Boolean).sort((a, b) => a.localeCompare(b));
  }, [sourceCounts, meta]);
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
  const geoSummaryPrincipal = useMemo(
    () => summarizeByGeo(principalItems),
    [principalItems],
  );
  const topSources = useMemo(() => topCounts(items, (i) => i.source), [items]);
  const topActores = useMemo(
    () =>
      topCounts(
        items.filter(
          (item) => !isPrincipalName(item.actor || "", principalAliasKeys),
        ),
        (i) => i.actor || "Sin actor",
      ),
    [items, principalAliasKeys],
  );
  const sentimentSeries = useMemo(
    () =>
      buildComparativeSeries(
        chartItems,
        effectiveActor,
        principalAliasKeys,
        effectiveFromDate,
        effectiveToDate,
      ),
    [chartItems, effectiveActor, principalAliasKeys, effectiveFromDate, effectiveToDate],
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
      effectiveActor !== "all" && !isPrincipalName(effectiveActor, principalAliasKeys)
        ? effectiveActor
        : null,
    [effectiveActor, principalAliasKeys],
  );
  const selectedActorKey = useMemo(
    () => (selectedActor ? normalizeKey(selectedActor) : null),
    [selectedActor],
  );
  const storeSourcesEnabled = useMemo(
    () => new Set((meta?.sources_enabled ?? []).map((src) => src.toLowerCase())),
    [meta?.sources_enabled],
  );
  const appleStoreEnabled = storeSourcesEnabled.has("appstore");
  const googlePlayEnabled = storeSourcesEnabled.has("google_play");
  const showStoreRatings = appleStoreEnabled || googlePlayEnabled;
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
  const stackSentimentSummary = isDashboard && showStoreRatingsForGeo;
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
  const dashboardMentions = useMemo(() => {
    const sentimentBase = isDashboard
      ? groupedMentions.filter((item) => isPrincipalGroup(item, principalAliasKeys))
      : groupedMentions;
    const sentimentMentions = sentimentBase.map((group) => ({
      key: `sentiment:${group.key}`,
      kind: "sentiment" as const,
      title: group.title,
      text: group.text,
      geo: group.geo,
      actor: group.actor,
      sentiment: group.sentiment,
      rating: group.rating ?? null,
      date: group.published_at || group.collected_at || null,
      sources: group.sources.map((src) => src.name),
    }));
    return sentimentMentions
      .sort((a, b) => {
        const da = a.date || "";
        const db = b.date || "";
        return db.localeCompare(da);
      })
      .slice(0, 20);
  }, [groupedMentions, isDashboard, principalAliasKeys]);
  const [mentionsTab, setMentionsTab] = useState<"principal" | "actor">("principal");

  const mentionsToShow =
    mentionsTab === "principal" ? principalMentions : actorMentions;
  const mentionsLabel = mentionsTab === "principal" ? principalLabel : actorLabel;
  const errorMessage = error || chartError;
  const mentionsLoading = itemsLoading || chartLoading;
  const headerEyebrow = mode === "dashboard" ? "Dashboard" : "Panorama reputacional";
  const headerTitle =
    mode === "dashboard" ? "Dashboard reputacional" : "Sentimiento histórico";
  const headerSubtitle =
    mode === "dashboard"
      ? "Señales de percepción y salud operativa en un mismo vistazo."
      : "Analiza la conversación por país, periodo y fuente. Detecta señales tempranas y compara impacto entre entidades.";

  const showManualIngest = !AUTH_ENABLED;

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
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Calendar className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Rango: {rangeLabel}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <MessageSquare className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Menciones:{" "}
              {itemsLoading ? (
                <LoadingPill className="h-2 w-12" label="Cargando menciones" />
              ) : (
                items.length
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
                {showManualIngest
                  ? "Aún no hay datos disponibles. Lanza una ingesta para generar el histórico."
                  : "Aún no hay datos disponibles. La ingesta manual está deshabilitada en este entorno."}
              </div>
              {reputationIngestNote && (
                <div className="mt-1 text-[10px] text-[color:var(--text-50)]">
                  {reputationIngestNote}
                </div>
              )}
            </div>
            {showManualIngest && (
              <button
                type="button"
                onClick={handleStartReputationIngest}
                disabled={reputationIngesting}
                className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--ink)] transition hover:shadow-[var(--shadow-soft)] disabled:opacity-70"
              >
                {reputationIngesting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Iniciar ingesta
              </button>
            )}
          </div>
        </div>
      )}

      {errorMessage && (
        <div className="mt-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {errorMessage}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-4">
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
            {!isDashboard && (
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
                const countLabel =
                  typeof count === "number" ? count.toLocaleString("es-ES") : null;
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
                    {countLabel !== null && !itemsLoading && (
                      <span
                        className={
                          "ml-2 rounded-full px-2 py-0.5 text-[10px] font-semibold " +
                          (active
                            ? "bg-[color:var(--surface-15)] text-white"
                            : "bg-[color:var(--sand)] text-[color:var(--brand-ink)]")
                        }
                      >
                        {countLabel}
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

        <section
          className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise"
          style={{ animationDelay: "180ms" }}
        >
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
            RESUMEN
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <SummaryCard label="Total menciones" value={items.length} loading={itemsLoading} />
            <SummaryCard
              label="Score medio"
              value={sentimentSummary.avgScore.toFixed(2)}
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
            {showStoreRatingsForGeo && !isDashboard && (
              <StoreRatingCard
                label="Rating oficial competencia"
                ratings={actorStoreRatings}
                loading={itemsLoading}
                visibility={storeRatingVisibility}
                history={marketRatingsHistory}
                emptyLabel="Selecciona actor"
              />
            )}
            {stackSentimentSummary ? (
              <div className="flex flex-col gap-3">
                <SummaryCard
                  label="Positivas"
                  value={sentimentSummary.positive}
                  loading={itemsLoading}
                />
                <SummaryCard
                  label="Negativas"
                  value={sentimentSummary.negative}
                  loading={itemsLoading}
                />
              </div>
            ) : (
              <>
                <SummaryCard
                  label="Positivas"
                  value={sentimentSummary.positive}
                  loading={itemsLoading}
                />
                <SummaryCard
                  label="Negativas"
                  value={sentimentSummary.negative}
                  loading={itemsLoading}
                />
              </>
            )}
          </div>
          {!isDashboard && (
            <div className="mt-5">
              <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                TOP FUENTES
              </div>
              <div className="mt-2 space-y-2">
                {itemsLoading ? (
                  <SkeletonRows count={4} />
                ) : (
                  (() => {
                    const maxValue = Math.max(1, ...topSources.map((row) => row.count));
                    return topSources.map((row) => (
                      <RowMeter
                        key={row.key}
                        label={row.key}
                        value={row.count}
                        maxValue={maxValue}
                      />
                    ));
                  })()
                )}
              </div>
            </div>
          )}
          {!isDashboard && (
            <div className="mt-4">
              <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                TOP OTROS ACTORES DEL MERCADO
              </div>
              <div className="mt-2 space-y-2">
                {itemsLoading ? (
                  <SkeletonRows count={4} />
                ) : (
                  (() => {
                    const maxValue = Math.max(1, ...topActores.map((row) => row.count));
                    return topActores.map((row) => (
                      <RowMeter
                        key={row.key}
                        label={row.key}
                        value={row.count}
                        maxValue={maxValue}
                      />
                    ));
                  })()
                )}
              </div>
            </div>
          )}
        </section>
      </div>

      {!isDashboard && (
        <section className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "240ms" }}>
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
            {`SENTIMIENTO POR PAÍS: ${actorPrincipalName}`}
          </div>
          <div className="mt-3 overflow-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-45)]">
                  <th className="py-2 pr-4">País</th>
                  <th className="py-2 pr-4">Menciones</th>
                  <th className="py-2 pr-4">Score medio</th>
                  <th className="py-2 pr-4">Positivas</th>
                  <th className="py-2 pr-4">Neutrales</th>
                  <th className="py-2">Negativas</th>
                </tr>
              </thead>
              <tbody>
                {itemsLoading ? (
                  <SkeletonTableRows columns={6} rows={3} />
                ) : (
                  geoSummaryPrincipal.map((row) => (
                    <tr key={row.geo} className="border-t border-[color:var(--border-60)]">
                      <td className="py-2 pr-4 font-semibold text-[color:var(--ink)]">
                        {row.geo}
                      </td>
                      <td className="py-2 pr-4">{row.count}</td>
                      <td className="py-2 pr-4">{row.avgScore.toFixed(2)}</td>
                      <td className="py-2 pr-4">{row.positive}</td>
                      <td className="py-2 pr-4">{row.neutral}</td>
                      <td className="py-2">{row.negative}</td>
                    </tr>
                  ))
                )}
                {!itemsLoading && !geoSummaryPrincipal.length && (
                  <tr>
                    <td className="py-3 text-sm text-[color:var(--text-45)]" colSpan={6}>
                      No hay datos para los filtros seleccionados.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "300ms" }}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
            {mode === "dashboard" ? "SENTIMIENTO" : "ÍNDICE REPUTACIONAL ACUMULADO"}
          </div>
          <div className="text-xs text-[color:var(--text-55)]">
            {mode === "dashboard"
              ? `${principalLabel} · ${rangeLabel}`
              : `Comparativa ${principalLabel} vs ${actorLabel} · ${rangeLabel}`}
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
            />
          )}
        </div>
      </section>


      {mode === "dashboard" ? (
        <section className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "360ms" }}>
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
              ÚLTIMAS MENCIONES
            </div>
            <div className="text-xs text-[color:var(--text-50)]">
              {mentionsLoading ? (
                <LoadingPill className="h-2 w-24" label="Cargando menciones" />
              ) : (
                <>
                  Mostrando {dashboardMentions.length} recientes ·{" "}
                  Sentimiento
                </>
              )}
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {mentionsLoading && (
              <div className="text-sm text-[color:var(--text-50)]">Cargando sentimiento…</div>
            )}
            {!mentionsLoading &&
              dashboardMentions.map((item, index) => (
                <DashboardMentionCard
                  key={item.key}
                  item={item}
                  index={index}
                  principalLabel={actorPrincipalName}
                />
              ))}
            {!mentionsLoading && !dashboardMentions.length && (
              <div className="text-sm text-[color:var(--text-45)]">
                No hay menciones para mostrar.
              </div>
            )}
          </div>
        </section>
      ) : (
        <section className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "360ms" }}>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
              LISTADO COMPLETO
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
                  (mentionsTab === "principal"
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
              <button
                onClick={() => setMentionsTab("actor")}
                className={
                  "group w-full sm:w-auto flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2 rounded-full px-3 py-1.5 text-xs font-semibold transition sm:hover:-translate-y-0.5 " +
                  (mentionsTab === "actor"
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
                    activeTab: mentionsTab,
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
}: {
  label: string;
  value: number | string;
  loading?: boolean;
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-4 py-3 shadow-[var(--shadow-soft)]">
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

function StoreRatingCard({
  label,
  ratings,
  loading = false,
  visibility,
  emptyLabel = "—",
  history,
}: {
  label: string;
  ratings: ActorStoreRatings | null;
  loading?: boolean;
  visibility: { showApple: boolean; showGoogle: boolean };
  emptyLabel?: string;
  history?: MarketRating[];
}) {
  const showApple = visibility.showApple;
  const showGoogle = visibility.showGoogle;
  const showRows = showApple || showGoogle;
  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-4 py-3 shadow-[var(--shadow-soft)]">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[color:var(--aqua)] via-[color:var(--blue)] to-transparent" />
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-45)]">
        {label}
      </div>
      {loading ? (
        <div className="mt-3 space-y-2">
          <LoadingPill className="h-8 w-full" label={`Cargando ${label}`} />
          <LoadingPill className="h-8 w-5/6" label={`Cargando ${label}`} />
        </div>
      ) : !ratings ? (
        <div className="mt-3 text-sm text-[color:var(--text-55)]">{emptyLabel}</div>
      ) : (
        <div className="mt-3 mt-auto space-y-2">
          {showRows && showApple && (
            <StoreRatingRow
              icon={<AppleMark className="h-5 w-5" />}
              current={ratings.appstore ?? null}
              history={history}
              tone="apple"
            />
          )}
          {showRows && showGoogle && (
            <StoreRatingRow
              icon={<AndroidMark className="h-5 w-5" />}
              current={ratings.google_play ?? null}
              history={history}
              tone="google"
            />
          )}
          {!showRows && (
            <div className="text-sm text-[color:var(--text-55)]">—</div>
          )}
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
}: {
  icon: ReactNode;
  current: MarketRating | null;
  history?: MarketRating[];
  tone: "apple" | "google";
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
      <div
        className={`text-right text-lg font-display font-semibold ${
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

function RowMeter({
  label,
  value,
  maxValue,
}: {
  label: string;
  value: number;
  maxValue: number;
}) {
  const safeMax = Math.max(1, maxValue);
  const ratio = Math.min(1, value / safeMax);
  return (
    <div className="flex items-center gap-3">
      <div className="w-28 text-xs text-[color:var(--text-55)] truncate">{label}</div>
      <div className="flex-1 h-2 rounded-full bg-[color:var(--surface-70)] overflow-hidden border border-[color:var(--border-70)]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[color:var(--blue)] to-[color:var(--aqua)]"
          style={{ width: `${Math.round(ratio * 100)}%` }}
        />
      </div>
      <div className="w-8 text-right text-xs text-[color:var(--text-55)]">{value}</div>
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

function SkeletonTableRows({ columns, rows }: { columns: number; rows: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <tr key={rowIdx} className="border-t border-[color:var(--border-60)] animate-pulse">
          {Array.from({ length: columns }).map((_, colIdx) => (
            <td key={colIdx} className="py-2 pr-4">
              <div className="h-3 w-full max-w-[120px] rounded-full bg-[color:var(--surface-70)] border border-[color:var(--border-60)]" />
            </td>
          ))}
        </tr>
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
  sentiment?: string;
  rating?: number | null;
  rating_source?: string | null;
  published_at?: string | null;
  collected_at?: string | null;
  sources: MentionSource[];
  count: number;
  manual_override?: ManualOverride | null;
};

function MentionCard({
  item,
  index,
  principalLabel,
  geoOptions,
  onOverride,
}: {
  item: MentionGroup;
  index: number;
  principalLabel: string;
  geoOptions: string[];
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
  const ratingLabel = ratingValue ? ratingValue.toFixed(1) : null;
  const blockedSources = item.sources.filter((src) => isManualOverrideBlockedSource(src));
  const ratingSourceKey = normalizeSourceKey(item.rating_source ?? "");
  const manualOverrideBlocked =
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
    return host.includes("itunes.apple.com") || host.includes("apps.apple.com");
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
    const title = cleanText(item.title || "");
    const text = cleanText(item.text || "");
    const base =
      title || text || item.url || String(item.id ?? "sin-titulo");
    const key = [
      normalizeKey(base),
      item.geo || "",
      extractedActor || "",
    ].join("|");

    if (!map.has(key)) {
      map.set(key, {
        key,
        ids: [],
        title: title || text || "Sin título",
        text: text || undefined,
        geo: item.geo || undefined,
        actor: extractedActor || undefined,
        sentiment: item.sentiment || undefined,
        rating: extractRating(item),
        rating_source: extractRatingSource(item),
        published_at: item.published_at || null,
        collected_at: item.collected_at || null,
        sources: [],
        count: 0,
        manual_override: item.manual_override ?? undefined,
      });
    }

    const group = map.get(key);
    if (!group) continue;

    group.count += 1;
    if (item.id && !group.ids.includes(item.id)) {
      group.ids.push(item.id);
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
  const raw = signals.rating;
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string") {
    const parsed = Number(raw.replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
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

function summarizeByGeo(items: ReputationItem[]) {
  const map = new Map<
    string,
    { count: number; positive: number; neutral: number; negative: number; score: number; scored: number }
  >();

  for (const item of items) {
    const geo = item.geo || "Sin país";
    if (!map.has(geo)) {
      map.set(geo, { count: 0, positive: 0, neutral: 0, negative: 0, score: 0, scored: 0 });
    }
    const entry = map.get(geo);
    if (!entry) continue;
    entry.count += 1;
    if (item.sentiment === "positive") entry.positive += 1;
    if (item.sentiment === "neutral") entry.neutral += 1;
    if (item.sentiment === "negative") entry.negative += 1;
    const score = Number((item.signals as Record<string, unknown>)?.sentiment_score);
    if (!Number.isNaN(score)) {
      entry.score += score;
      entry.scored += 1;
    }
  }

  return Array.from(map.entries())
    .map(([geo, entry]) => ({
      geo,
      count: entry.count,
      positive: entry.positive,
      neutral: entry.neutral,
      negative: entry.negative,
      avgScore: entry.scored ? entry.score / entry.scored : 0,
    }))
    .sort((a, b) => b.count - a.count);
}

function topCounts(items: ReputationItem[], getKey: (item: ReputationItem) => string) {
  const map = new Map<string, number>();
  for (const item of items) {
    const key = getKey(item);
    map.set(key, (map.get(key) || 0) + 1);
  }
  return Array.from(map.entries())
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
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

function DashboardMentionCard({
  item,
  index,
  principalLabel,
}: {
  item: DashboardMention;
  index: number;
  principalLabel: string;
}) {
  const displayDate = formatDate(item.date || null);
  const sentimentTone = getSentimentTone(item.sentiment);
  const ratingValue = typeof item.rating === "number" ? item.rating : null;
  const title = cleanText(item.title) || "Sin título";
  const text = cleanText(item.text);

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
        <span className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-2.5 py-1">
          <Calendar className="h-3.5 w-3.5 text-[color:var(--blue)]" />
          {displayDate}
        </span>
        {sentimentTone && (
          <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 ${sentimentTone.className}`}>
            {sentimentTone.icon}
            {sentimentTone.label}
          </span>
        )}
        {ratingValue !== null && (
          <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--aqua)]/40 [background-image:var(--gradient-chip)] px-2.5 py-1 text-[11px] text-[color:var(--brand-ink)] shadow-[var(--shadow-pill)]">
            <StarMeter rating={ratingValue} />
            <span className="font-semibold">{ratingValue.toFixed(1)}</span>
            <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-45)]">/5</span>
          </span>
        )}
      </div>
      <div className="mt-3 text-sm font-semibold text-[color:var(--ink)]">
        {title}
      </div>
      {text && (
        <p className="mt-2 text-sm text-[color:var(--text-60)] line-clamp-3">{text}</p>
      )}
    </article>
  );
}

function downloadChartCsv(
  data: { date: string; principal: number | null; actor: number | null }[],
  principalLabel: string,
  actorLabel: string,
  filename: string,
) {
  const headers = ["Fecha", principalLabel, actorLabel];
  const rows = data.map((row) => [
    row.date,
    typeof row.principal === "number" ? row.principal.toFixed(3) : "",
    typeof row.actor === "number" ? row.actor.toFixed(3) : "",
  ]);
  downloadCsv(filename, headers, rows);
}

const MENTIONS_HEADERS = [
  "ids",
  "titulo",
  "texto",
  "pais",
  "actor",
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
}: {
  principalItems: MentionGroup[];
  actorItems: MentionGroup[];
  principalLabel: string;
  actorLabel: string;
  filename: string;
  activeTab: "principal" | "actor";
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
  const sheets = activeTab === "actor" ? [actorSheet, principalSheet] : [principalSheet, actorSheet];

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
