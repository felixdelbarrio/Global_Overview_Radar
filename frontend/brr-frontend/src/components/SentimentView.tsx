"use client";

/**
 * Vista de sentimiento historico por pais / periodo / fuente.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Formatter } from "recharts/types/component/DefaultTooltipContent";
import type { ValueType } from "recharts/types/component/DefaultTooltipContent";
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
  X,
} from "lucide-react";
import { Shell } from "@/components/Shell";
import { apiGet, apiPost } from "@/lib/api";
import { INCIDENTS_FEATURE_ENABLED } from "@/lib/flags";
import type {
  ActorPrincipalMeta,
  EvolutionPoint,
  ReputationCacheDocument,
  ReputationItem,
  ReputationMeta,
} from "@/lib/types";

const SENTIMENTS = ["all", "positive", "neutral", "negative"] as const;

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

type IncidentItem = {
  global_id: string;
  title: string;
  status: string;
  severity: string;
  opened_at?: string | null;
  updated_at?: string | null;
  closed_at?: string | null;
  product?: string | null;
  feature?: string | null;
};

type DashboardMention = {
  key: string;
  kind: "sentiment" | "incident";
  title: string;
  text?: string;
  geo?: string;
  actor?: string;
  sentiment?: string | null;
  rating?: number | null;
  date?: string | null;
  sources?: string[];
  severity?: string;
  status?: string;
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
  const [sources, setSources] = useState<string[]>([]);
  const [overrideRefresh, setOverrideRefresh] = useState(0);
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
  const incidentsAvailable = meta?.incidents_available === true;
  const incidentsEnabled =
    INCIDENTS_FEATURE_ENABLED && incidentsAvailable && meta?.ui?.incidents_enabled !== false;
  const showIncidents = mode === "dashboard" && incidentsEnabled;
  const showDownloads = mode === "sentiment";
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [incidentsSeries, setIncidentsSeries] = useState<EvolutionPoint[]>([]);
  const [incidentsError, setIncidentsError] = useState<string | null>(null);

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

  const handleOverride = async (payload: OverridePayload) => {
    await apiPost<{ updated: number }>("/reputation/items/override", payload);
    setOverrideRefresh((value) => value + 1);
  };

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
    apiGet<ReputationMeta>("/reputation/meta")
      .then((meta) => {
        if (!alive) return;
        setActorPrincipal(meta.actor_principal ?? null);
        setMeta(meta);
      })
      .catch(() => {
        if (alive) {
          setActorPrincipal(null);
          setMeta(null);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!showIncidents) {
      setIncidents([]);
      setIncidentsSeries([]);
      setIncidentsError(null);
      return;
    }
    let alive = true;

    apiGet<{ items: IncidentItem[] }>("/incidents?sort=updated_desc&limit=200")
      .then((payload) => {
        if (!alive) return;
        setIncidents(payload.items ?? []);
      })
      .catch((e) => {
        if (alive) setIncidentsError(String(e));
      });

    const days = computeEvolutionDays(effectiveFromDate, effectiveToDate, today);
    apiGet<{ days: number; series: EvolutionPoint[] }>(`/evolution?days=${days}`)
      .then((payload) => {
        if (!alive) return;
        setIncidentsSeries(payload.series ?? []);
      })
      .catch((e) => {
        if (alive) setIncidentsError(String(e));
      });

    return () => {
      alive = false;
    };
  }, [showIncidents, effectiveFromDate, effectiveToDate, today]);

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
  }, [effectiveFromDate, effectiveToDate, effectiveSentiment, geo, sources, overrideRefresh]);

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
  const geoSummary = useMemo(() => summarizeByGeo(items), [items]);
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
      buildDashboardSeries(
        sentimentSeries,
        incidentsSeries,
        effectiveFromDate,
        effectiveToDate,
        showIncidents,
      ),
    [sentimentSeries, incidentsSeries, effectiveFromDate, effectiveToDate, showIncidents],
  );
  const incidentsSummary = useMemo(() => {
    if (!showIncidents || !incidentsSeries.length) {
      return { open: 0, newTotal: 0, closedTotal: 0 };
    }
    const last = incidentsSeries[incidentsSeries.length - 1];
    return {
      open: last?.open ?? 0,
      newTotal: incidentsSeries.reduce((acc, row) => acc + (row.new ?? 0), 0),
      closedTotal: incidentsSeries.reduce((acc, row) => acc + (row.closed ?? 0), 0),
    };
  }, [showIncidents, incidentsSeries]);
  const incidentsSummaryLoading =
    showIncidents && !incidentsSeries.length && !incidentsError;
  const groupedMentions = useMemo(() => groupMentions(items), [items]);
  const rangeLabel = useMemo(
    () => buildRangeLabel(effectiveFromDate, effectiveToDate),
    [effectiveFromDate, effectiveToDate],
  );
  const latestTimestamp = useMemo(() => getLatestDate(items), [items]);
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
    const incidentMentions = showIncidents
      ? incidents.map((it) => ({
          key: `incident:${it.global_id}`,
          kind: "incident" as const,
          title: it.title || it.global_id,
          text: [it.product, it.feature].filter(Boolean).join(" · ") || undefined,
          date: it.updated_at || it.opened_at || it.closed_at || null,
          severity: it.severity,
          status: it.status,
        }))
      : [];

    return [...sentimentMentions, ...incidentMentions]
      .sort((a, b) => {
        const da = a.date || "";
        const db = b.date || "";
        return db.localeCompare(da);
      })
      .slice(0, 20);
  }, [groupedMentions, incidents, showIncidents, isDashboard, principalAliasKeys]);
  const [mentionsTab, setMentionsTab] = useState<"principal" | "actor">("principal");

  const mentionsToShow =
    mentionsTab === "principal" ? principalMentions : actorMentions;
  const mentionsLabel = mentionsTab === "principal" ? principalLabel : actorLabel;
  const errorMessage = error || chartError || incidentsError;
  const mentionsLoading = itemsLoading || chartLoading;
  const headerEyebrow = mode === "dashboard" ? "Dashboard" : "Panorama reputacional";
  const headerTitle =
    mode === "dashboard" ? "Dashboard reputacional" : "Sentimiento histórico";
  const headerSubtitle =
    mode === "dashboard"
      ? "Señales de percepción y salud operativa en un mismo vistazo."
      : "Analiza la conversación por país, periodo y fuente. Detecta señales tempranas y compara impacto entre entidades.";

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
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[color:var(--blue)]" />
              ) : (
                items.length
              )}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Clock className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Última actualización:{" "}
              {itemsLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[color:var(--blue)]" />
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
            <FilterField label="Entidad">
              <div className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)]">
                {actorPrincipalName}
              </div>
            </FilterField>
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
                      <span
                        className={
                          "ml-2 rounded-full px-2 py-0.5 text-[10px] font-semibold " +
                          (active
                            ? "bg-[color:var(--surface-15)] text-white"
                            : "bg-[color:var(--sand)] text-[color:var(--brand-ink)]")
                        }
                      >
                        <Loader2 className="h-3 w-3 animate-spin" />
                      </span>
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
            <SummaryCard label="Positivas" value={sentimentSummary.positive} loading={itemsLoading} />
            <SummaryCard label="Negativas" value={sentimentSummary.negative} loading={itemsLoading} />
          </div>
          {isDashboard && showIncidents && (
            <>
              <div className="mt-4 text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                INCIDENCIAS · ÚLTIMOS 30 DÍAS
              </div>
              <div className="mt-2 grid grid-cols-2 gap-3">
                <SummaryCard
                  label="Abiertas"
                  value={incidentsSummary.open}
                  loading={incidentsSummaryLoading}
                />
                <SummaryCard
                  label="Nuevas"
                  value={incidentsSummary.newTotal}
                  loading={incidentsSummaryLoading}
                />
                <SummaryCard
                  label="Cerradas"
                  value={incidentsSummary.closedTotal}
                  loading={incidentsSummaryLoading}
                />
              </div>
            </>
          )}
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
            SENTIMIENTO POR PAÍS
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
                  geoSummary.map((row) => (
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
                {!itemsLoading && !geoSummary.length && (
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
            {mode === "dashboard"
              ? showIncidents
                ? "SENTIMIENTO VS INCIDENCIAS"
                : "SENTIMIENTO"
              : "ÍNDICE REPUTACIONAL ACUMULADO"}
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
        <div className="mt-3 h-72 min-h-[240px]">
          {chartLoading ? (
            <div className="h-full rounded-[22px] border border-[color:var(--border-60)] bg-[color:var(--surface-70)] animate-pulse" />
          ) : mode === "dashboard" ? (
            <DashboardChart
              data={dashboardSeries}
              sentimentLabel={principalLabel}
              incidentsLabel={`Incidencias ${principalLabel}`}
              showIncidents={showIncidents}
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
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[color:var(--blue)]" />
                  Cargando menciones
                </span>
              ) : (
                <>
                  Mostrando {dashboardMentions.length} recientes ·{" "}
                  {showIncidents ? "Sentimiento + incidencias" : "Sentimiento"}
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
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
              LISTADO COMPLETO
            </div>
            <div className="text-xs text-[color:var(--text-50)]">
              {mentionsLoading ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[color:var(--blue)]" />
                  Cargando resultados
                </span>
              ) : (
                <>
                  Mostrando {mentionsToShow.length} resultados · {mentionsLabel}
                </>
              )}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-70)] p-1 shadow-[var(--shadow-soft)]">
            <button
              onClick={() => setMentionsTab("principal")}
              className={
                "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold transition " +
                (mentionsTab === "principal"
                  ? "bg-[color:var(--surface-solid)] text-[color:var(--ink)] shadow-[var(--shadow-sm)]"
                  : "text-[color:var(--text-50)] hover:text-[color:var(--ink)]")
              }
            >
              <span className="inline-block h-1.5 w-7 rounded-full bg-[#004481]" />
              {principalLabel}
              <span className="text-[10px] text-[color:var(--text-40)]">
                {principalMentions.length} resultados
              </span>
            </button>
            <button
              onClick={() => setMentionsTab("actor")}
              className={
                "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold transition " +
                (mentionsTab === "actor"
                  ? "bg-[color:var(--surface-solid)] text-[color:var(--ink)] shadow-[var(--shadow-sm)]"
                  : "text-[color:var(--text-50)] hover:text-[color:var(--ink)]")
              }
            >
              <span className="inline-block h-[3px] w-7 rounded-full border-t-2 border-dashed border-[#2dcccd]" />
              {actorLabel}
              <span className="text-[10px] text-[color:var(--text-40)]">
                {actorMentions.length} resultados
              </span>
            </button>
            {showDownloads && (
              <button
                onClick={() =>
                  downloadMentionsCsv(
                    mentionsToShow,
                    buildDownloadName("sentimiento_listado", fromDate, toDate),
                  )
                }
                className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--brand-ink)] shadow-[var(--shadow-pill)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pill-hover)]"
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
          <span className="inline-flex items-center gap-2 text-sm text-[color:var(--text-40)]">
            <Loader2 className="h-4 w-4 animate-spin text-[color:var(--blue)]" />
            Cargando
          </span>
        ) : (
          value
        )}
      </div>
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
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-[color:var(--text-45)]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-40)]">
            Fuentes
          </span>
          {item.sources.map((src) =>
            src.url ? (
              <a
                key={src.name}
                href={src.url}
                target="_blank"
                rel="noreferrer"
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
            ),
          )}
        </div>
        {item.sources[0]?.url && (
          <a
            href={item.sources[0].url}
            target="_blank"
            rel="noreferrer"
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

function SentimentChart({
  data,
  principalLabel,
  actorLabel,
}: {
  data: { date: string; principal: number | null; actor: number | null }[];
  principalLabel: string;
  actorLabel: string;
}) {
  const tooltipFormatter: Formatter<ValueType, string | number> = (value) => {
    if (typeof value === "number") {
      return value.toFixed(2);
    }
    return value ?? "";
  };

  if (!data.length) {
    return (
      <div className="h-full grid place-items-center text-sm text-[color:var(--text-45)]">
        No hay datos para el periodo seleccionado.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(d: string) => d.slice(5)}
          fontSize={11}
        />
        <YAxis
          domain={["auto", "auto"]}
          fontSize={11}
          tickFormatter={(v: number) => v.toFixed(2)}
        />
        <ReferenceLine y={0} stroke="var(--chart-reference)" strokeDasharray="3 3" />
        <Tooltip
          formatter={tooltipFormatter}
          labelFormatter={(label) => `Fecha ${String(label ?? "")}`}
          contentStyle={{
            borderRadius: 16,
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-tooltip)",
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="principal"
          name={principalLabel}
          stroke="#004481"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="actor"
          name={actorLabel}
          stroke="#2dcccd"
          strokeWidth={2}
          dot={false}
          strokeDasharray="6 4"
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function DashboardChart({
  data,
  sentimentLabel,
  incidentsLabel,
  showIncidents,
}: {
  data: { date: string; sentiment: number | null; incidents: number | null }[];
  sentimentLabel: string;
  incidentsLabel: string;
  showIncidents: boolean;
}) {
  const tooltipFormatter: Formatter<ValueType, string | number> = (value) => {
    if (typeof value === "number") {
      return value.toFixed(2);
    }
    return value ?? "";
  };

  if (!data.length) {
    return (
      <div className="h-full grid place-items-center text-sm text-[color:var(--text-45)]">
        No hay datos para el periodo seleccionado.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
        <YAxis yAxisId="sentiment" fontSize={11} />
        {showIncidents && (
          <YAxis yAxisId="incidents" orientation="right" fontSize={11} />
        )}
        <Tooltip
          formatter={tooltipFormatter}
          contentStyle={{
            borderRadius: 16,
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-tooltip)",
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="sentiment"
          name={sentimentLabel}
          stroke="#004481"
          strokeWidth={2.5}
          dot={false}
          yAxisId="sentiment"
          connectNulls
        />
        {showIncidents && (
          <Line
            type="monotone"
            dataKey="incidents"
            name={incidentsLabel}
            stroke="#2dcccd"
            strokeWidth={2}
            dot={false}
            yAxisId="incidents"
            connectNulls
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
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
  const sentimentTone = item.kind === "sentiment" ? getSentimentTone(item.sentiment) : null;
  const severityTone = item.kind === "incident" ? getIncidentSeverityTone(item.severity) : null;
  const statusTone = item.kind === "incident" ? getIncidentStatusTone(item.status) : null;
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
        {item.kind === "sentiment" && sentimentTone && (
          <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 ${sentimentTone.className}`}>
            {sentimentTone.icon}
            {sentimentTone.label}
          </span>
        )}
        {item.kind === "incident" && severityTone && (
          <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 ${severityTone.className}`}>
            {severityTone.label}
          </span>
        )}
        {item.kind === "incident" && statusTone && (
          <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 ${statusTone.className}`}>
            {statusTone.label}
          </span>
        )}
        {item.kind === "sentiment" && ratingValue !== null && (
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

function computeEvolutionDays(
  fromDate?: string,
  toDate?: string,
  fallbackDate: Date = new Date(),
) {
  const end =
    toDate && !Number.isNaN(new Date(`${toDate}T00:00:00`).getTime())
      ? new Date(`${toDate}T00:00:00`)
      : fallbackDate;
  const safeEnd = end > fallbackDate ? fallbackDate : end;
  const start =
    fromDate && !Number.isNaN(new Date(`${fromDate}T00:00:00`).getTime())
      ? new Date(`${fromDate}T00:00:00`)
      : new Date(safeEnd);
  const diffMs = safeEnd.getTime() - start.getTime();
  const days = Math.max(1, Math.floor(diffMs / 86_400_000) + 1);
  return Math.min(days, 3650);
}

function buildDashboardSeries(
  sentimentSeries: { date: string; principal: number | null; actor: number | null }[],
  incidentsSeries: EvolutionPoint[],
  fromDate?: string,
  toDate?: string,
  showIncidents = true,
) {
  const sentimentMap = new Map(
    sentimentSeries.map((row) => [row.date, row.principal]),
  );
  const incidentsMap = new Map(
    incidentsSeries.map((row) => [row.date, row.open]),
  );

  const dates =
    sentimentSeries.length > 0
      ? sentimentSeries.map((row) => row.date)
      : buildDateRange(fromDate, toDate, incidentsSeries);

  return dates.map((date) => ({
    date,
    sentiment: sentimentMap.get(date) ?? null,
    incidents: showIncidents ? incidentsMap.get(date) ?? null : null,
  }));
}

function buildDateRange(
  fromDate?: string,
  toDate?: string,
  fallbackSeries: EvolutionPoint[] = [],
) {
  if (fromDate && toDate) {
    const start = new Date(`${fromDate}T00:00:00`);
    const end = new Date(`${toDate}T00:00:00`);
    if (!Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime())) {
      const result: string[] = [];
      const cursor = new Date(start);
      const endDate = end < start ? start : end;
      while (cursor <= endDate) {
        result.push(toDateInput(cursor));
        cursor.setDate(cursor.getDate() + 1);
      }
      return result;
    }
  }
  if (fallbackSeries.length) {
    return fallbackSeries.map((row) => row.date);
  }
  return [];
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

function downloadMentionsCsv(items: MentionGroup[], filename: string) {
  const headers = [
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
  const rows = items.map((item) => [
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
  downloadCsv(filename, headers, rows);
}

function buildDownloadName(prefix: string, fromDate?: string, toDate?: string) {
  const safePrefix = prefix.replace(/[^a-zA-Z0-9_-]+/g, "_");
  const rangeFrom = fromDate || "inicio";
  const rangeTo = toDate || "hoy";
  return `${safePrefix}_${rangeFrom}_${rangeTo}`;
}

function downloadCsv(filename: string, headers: string[], rows: (string | number | null | undefined)[][]) {
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

function getIncidentSeverityTone(severity?: string | null) {
  const sev = (severity || "UNKNOWN").toUpperCase();
  if (sev === "CRITICAL") {
    return {
      label: "Crítica",
      className: "bg-rose-50 text-rose-700 border-rose-200",
    };
  }
  if (sev === "HIGH") {
    return {
      label: "Alta",
      className: "bg-amber-50 text-amber-700 border-amber-200",
    };
  }
  if (sev === "MEDIUM") {
    return {
      label: "Media",
      className: "bg-blue-50 text-blue-700 border-blue-200",
    };
  }
  if (sev === "LOW") {
    return {
      label: "Baja",
      className: "bg-emerald-50 text-emerald-700 border-emerald-200",
    };
  }
  return {
    label: "Desconocida",
    className: "bg-slate-50 text-slate-600 border-slate-200",
  };
}

function getIncidentStatusTone(status?: string | null) {
  const st = (status || "UNKNOWN").toUpperCase();
  if (st === "OPEN") {
    return {
      label: "Abierta",
      className: "bg-sky-50 text-sky-700 border-sky-200",
    };
  }
  if (st === "IN_PROGRESS") {
    return {
      label: "En progreso",
      className: "bg-purple-50 text-purple-700 border-purple-200",
    };
  }
  if (st === "BLOCKED") {
    return {
      label: "Bloqueada",
      className: "bg-amber-50 text-amber-700 border-amber-200",
    };
  }
  if (st === "CLOSED") {
    return {
      label: "Cerrada",
      className: "bg-slate-50 text-slate-600 border-slate-200",
    };
  }
  return {
    label: "Desconocida",
    className: "bg-slate-50 text-slate-600 border-slate-200",
  };
}
