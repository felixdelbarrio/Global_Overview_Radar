"use client";

/**
 * Vista de sentimiento historico por pais / periodo / fuente.
 */

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
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
  Clock,
  MapPin,
  MessageSquare,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Minus,
} from "lucide-react";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { ReputationCacheDocument, ReputationItem } from "@/lib/types";

const SENTIMENTS = ["all", "positive", "neutral", "negative"] as const;

type SentimentFilter = (typeof SENTIMENTS)[number];

export default function SentimientoPage() {
  const today = useMemo(() => new Date(), []);
  const defaultTo = useMemo(() => toDateInput(today), [today]);
  const defaultFrom = useMemo(() => {
    const d = new Date(today);
    d.setFullYear(d.getFullYear() - 2);
    return toDateInput(d);
  }, [today]);

  const [items, setItems] = useState<ReputationItem[]>([]);
  const [chartItems, setChartItems] = useState<ReputationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [chartLoading, setChartLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);

  const [fromDate, setFromDate] = useState(defaultFrom);
  const [toDate, setToDate] = useState(defaultTo);
  const [sentiment, setSentiment] = useState<SentimentFilter>("all");
  const [entity, setEntity] = useState("bbva");
  const [geo, setGeo] = useState("all");
  const [actor, setActor] = useState("all");
  const [sources, setSources] = useState<string[]>([]);

  useEffect(() => {
    if (entity === "otros_actores" && isBbvaName(actor)) {
      setActor("all");
    }
    if (entity === "all" && isBbvaName(actor)) {
      setActor("all");
    }
  }, [entity, actor]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    if (sentiment !== "all") params.set("sentiment", sentiment);
    if (entity !== "all") params.set("entity", entity);
    if (geo !== "all") params.set("geo", geo);
    if (actor !== "all" && entity !== "bbva") {
      params.set("actor", actor);
    }
    if (sources.length) params.set("sources", sources.join(","));

    apiGet<ReputationCacheDocument>(`/reputation/items?${params.toString()}`)
      .then((doc) => {
        if (!alive) return;
        setItems(doc.items ?? []);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [fromDate, toDate, sentiment, entity, geo, actor, sources]);

  useEffect(() => {
    let alive = true;
    setChartLoading(true);
    setChartError(null);

    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    if (sentiment !== "all") params.set("sentiment", sentiment);
    if (geo !== "all") params.set("geo", geo);
    if (sources.length) params.set("sources", sources.join(","));

    apiGet<ReputationCacheDocument>(`/reputation/items?${params.toString()}`)
      .then((doc) => {
        if (!alive) return;
        setChartItems(doc.items ?? []);
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
  }, [fromDate, toDate, sentiment, geo, sources]);

  const sourcesOptions = useMemo(() => unique(items.map((i) => i.source)), [items]);
  const geoOptions = useMemo(
    () => unique(items.map((i) => i.geo).filter(Boolean) as string[]),
    [items],
  );
  const actorOptions = useMemo(() => {
    const values = unique(
      chartItems.map((i) => i.actor).filter(Boolean) as string[],
    );
    if (actor !== "all" && !values.includes(actor)) {
      values.push(actor);
      values.sort((a, b) => a.localeCompare(b));
    }
    if (entity === "otros_actores") return values.filter((v) => !isBbvaName(v));
    return values.filter((v) => !isBbvaName(v));
  }, [chartItems, entity, actor]);

  const sentimentSummary = useMemo(() => summarize(items), [items]);
  const geoSummary = useMemo(() => summarizeByGeo(items), [items]);
  const topSources = useMemo(() => topCounts(items, (i) => i.source), [items]);
  const topActores = useMemo(
    () => topCounts(items, (i) => i.actor || "Sin actor"),
    [items],
  );
  const sentimentSeries = useMemo(
    () => buildComparativeSeries(chartItems, actor),
    [chartItems, actor],
  );
  const groupedItems = useMemo(() => groupMentions(items), [items]);
  const rangeLabel = useMemo(
    () => buildRangeLabel(fromDate, toDate),
    [fromDate, toDate],
  );
  const latestTimestamp = useMemo(() => getLatestDate(items), [items]);
  const latestLabel = useMemo(
    () => formatDate(latestTimestamp),
    [latestTimestamp],
  );
  const bbvaLabel = useMemo(
    () => buildEntityLabel("BBVA", geo),
    [geo],
  );
  const actorLabel = useMemo(
    () =>
      buildEntityLabel(
        actor && actor !== "all" && !isBbvaName(actor)
          ? actor
          : "Otros actores del mercado",
        geo,
      ),
    [actor, geo],
  );

  return (
    <Shell>
      <section className="relative overflow-hidden rounded-[28px] border border-white/60 bg-[color:var(--panel-strong)] p-6 shadow-[0_30px_70px_rgba(7,33,70,0.12)] animate-rise">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-24 -right-10 h-48 w-48 rounded-full bg-[color:var(--bbva-aqua)]/15 blur-3xl" />
          <div className="absolute -bottom-16 left-10 h-40 w-40 rounded-full bg-[color:var(--bbva-blue)]/10 blur-3xl" />
        </div>
        <div className="relative">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/60 bg-white/70 px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-[color:var(--bbva-blue)] shadow-sm">
            <Sparkles className="h-3.5 w-3.5" />
            Panorama reputacional
          </div>
          <h1 className="mt-4 text-3xl sm:text-4xl font-display font-semibold text-[color:var(--bbva-ink)]">
            Sentimiento histórico
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-black/60">
            Analiza la conversación por país, periodo y fuente. Detecta señales
            tempranas y compara impacto entre entidades.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-black/55">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              <Calendar className="h-3.5 w-3.5 text-[color:var(--bbva-blue)]" />
              Rango: {rangeLabel}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              <MessageSquare className="h-3.5 w-3.5 text-[color:var(--bbva-blue)]" />
              Menciones: {items.length}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              <Clock className="h-3.5 w-3.5 text-[color:var(--bbva-blue)]" />
              Última actualización: {latestLabel}
            </span>
          </div>
        </div>
      </section>

      {(error || chartError) && (
        <div className="mt-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {error || chartError}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-4">
        <section
          className="rounded-[26px] border border-white/60 bg-[color:var(--panel)] p-5 shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl animate-rise"
          style={{ animationDelay: "120ms" }}
        >
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
            FILTROS PRINCIPALES
          </div>
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FilterField label="Desde">
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="w-full rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--bbva-ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none focus:border-[color:var(--bbva-aqua)]/60 focus:ring-2 focus:ring-[color:var(--bbva-aqua)]/30"
              />
            </FilterField>
            <FilterField label="Hasta">
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="w-full rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--bbva-ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none focus:border-[color:var(--bbva-aqua)]/60 focus:ring-2 focus:ring-[color:var(--bbva-aqua)]/30"
              />
            </FilterField>
            <FilterField label="Sentimiento">
              <select
                value={sentiment}
                onChange={(e) => setSentiment(e.target.value as SentimentFilter)}
                className="w-full rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--bbva-ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none focus:border-[color:var(--bbva-aqua)]/60 focus:ring-2 focus:ring-[color:var(--bbva-aqua)]/30"
              >
                {SENTIMENTS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt === "all" ? "Todos" : opt}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Entidad">
              <select
                value={entity}
                onChange={(e) => setEntity(e.target.value)}
                className="w-full rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--bbva-ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none focus:border-[color:var(--bbva-aqua)]/60 focus:ring-2 focus:ring-[color:var(--bbva-aqua)]/30"
              >
                <option value="bbva">BBVA</option>
                <option value="otros_actores">Otros actores del mercado</option>
                <option value="all">Todas</option>
              </select>
            </FilterField>
            <FilterField label="País">
              <select
                value={geo}
                onChange={(e) => setGeo(e.target.value)}
                className="w-full rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--bbva-ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none focus:border-[color:var(--bbva-aqua)]/60 focus:ring-2 focus:ring-[color:var(--bbva-aqua)]/30"
              >
                <option value="all">Todos</option>
                {geoOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Otros actores del mercado">
              <select
                value={actor}
                onChange={(e) => setActor(e.target.value)}
                className="w-full rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--bbva-ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none focus:border-[color:var(--bbva-aqua)]/60 focus:ring-2 focus:ring-[color:var(--bbva-aqua)]/30 disabled:opacity-60"
              >
                <option value="all">Todos</option>
                {actorOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </FilterField>
          </div>

          <div className="mt-4">
            <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
              FUENTES
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {sourcesOptions.map((src) => {
                const active = sources.includes(src);
                return (
                  <button
                    key={src}
                    onClick={() => toggleSource(src, sources, setSources)}
                    className={
                      "rounded-full px-3 py-1.5 text-xs border transition shadow-sm " +
                      (active
                        ? "bg-[color:var(--bbva-blue)] text-white border-transparent"
                        : "bg-white/80 text-[color:var(--bbva-navy)] border-white/60")
                    }
                  >
                    {src}
                  </button>
                );
              })}
              {!sourcesOptions.length && (
                <span className="text-xs text-black/40">
                  Sin datos disponibles
                </span>
              )}
            </div>
          </div>
        </section>

        <section
          className="rounded-[26px] border border-white/60 bg-[color:var(--panel)] p-5 shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl animate-rise"
          style={{ animationDelay: "180ms" }}
        >
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
            RESUMEN
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <SummaryCard label="Total menciones" value={items.length} />
            <SummaryCard
              label="Score medio"
              value={sentimentSummary.avgScore.toFixed(2)}
            />
            <SummaryCard label="Positivas" value={sentimentSummary.positive} />
            <SummaryCard label="Negativas" value={sentimentSummary.negative} />
          </div>
          <div className="mt-5">
            <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
              TOP FUENTES
            </div>
            <div className="mt-2 space-y-2">
              {topSources.map((row) => (
                <RowMeter key={row.key} label={row.key} value={row.count} />
              ))}
            </div>
          </div>
          <div className="mt-4">
            <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
              TOP OTROS ACTORES DEL MERCADO
            </div>
            <div className="mt-2 space-y-2">
              {topActores.map((row) => (
                <RowMeter key={row.key} label={row.key} value={row.count} />
              ))}
            </div>
          </div>
        </section>
      </div>

      <section className="mt-6 rounded-[26px] border border-white/60 bg-[color:var(--panel)] p-5 shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl animate-rise" style={{ animationDelay: "240ms" }}>
        <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
          SENTIMIENTO POR PAÍS
        </div>
        <div className="mt-3 overflow-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.2em] text-black/45">
                <th className="py-2 pr-4">País</th>
                <th className="py-2 pr-4">Menciones</th>
                <th className="py-2 pr-4">Score medio</th>
                <th className="py-2 pr-4">Positivas</th>
                <th className="py-2 pr-4">Neutrales</th>
                <th className="py-2">Negativas</th>
              </tr>
            </thead>
            <tbody>
              {geoSummary.map((row) => (
                <tr key={row.geo} className="border-t border-white/60">
                  <td className="py-2 pr-4 font-semibold text-[color:var(--bbva-ink)]">
                    {row.geo}
                  </td>
                  <td className="py-2 pr-4">{row.count}</td>
                  <td className="py-2 pr-4">{row.avgScore.toFixed(2)}</td>
                  <td className="py-2 pr-4">{row.positive}</td>
                  <td className="py-2 pr-4">{row.neutral}</td>
                  <td className="py-2">{row.negative}</td>
                </tr>
              ))}
              {!geoSummary.length && (
                <tr>
                  <td className="py-3 text-sm text-black/45" colSpan={6}>
                    No hay datos para los filtros seleccionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-6 rounded-[26px] border border-white/60 bg-[color:var(--panel)] p-5 shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl animate-rise" style={{ animationDelay: "300ms" }}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
            EVOLUCIÓN DE REPUTACIÓN
          </div>
          <div className="text-xs text-black/55">
            Comparativa {bbvaLabel} vs {actorLabel} · {rangeLabel}
          </div>
        </div>
        <div className="mt-3 h-72 min-h-[240px]">
          {chartLoading ? (
            <div className="h-full rounded-[22px] border border-white/60 bg-white/70 animate-pulse" />
          ) : (
            <SentimentChart
              data={sentimentSeries}
              bbvaLabel={bbvaLabel}
              actorLabel={actorLabel}
            />
          )}
        </div>
      </section>

      <section className="mt-6 rounded-[26px] border border-white/60 bg-[color:var(--panel)] p-5 shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl animate-rise" style={{ animationDelay: "360ms" }}>
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
          ÚLTIMAS MENCIONES
          </div>
          <div className="text-xs text-black/50">
            Mostrando las 20 más recientes
          </div>
        </div>
        <div className="mt-4 space-y-3">
          {loading && (
            <div className="text-sm text-black/50">Cargando sentimiento…</div>
          )}
          {!loading &&
            groupedItems.slice(0, 20).map((item, index) => (
              <MentionCard
                key={item.key}
                item={item}
                index={index}
              />
            ))}
          {!loading && !groupedItems.length && (
            <div className="text-sm text-black/45">
              No hay menciones para mostrar.
            </div>
          )}
        </div>
      </section>
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
    <label className="text-[11px] uppercase tracking-[0.18em] text-black/50">
      <span className="block mb-2">{label}</span>
      {children}
    </label>
  );
}

function SummaryCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/70 bg-white/80 px-4 py-3 shadow-[0_10px_30px_rgba(7,33,70,0.08)]">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[color:var(--bbva-aqua)] via-[color:var(--bbva-blue)] to-transparent" />
      <div className="text-[11px] uppercase tracking-[0.16em] text-black/45">
        {label}
      </div>
      <div className="mt-2 text-2xl font-display font-semibold text-[color:var(--bbva-ink)]">
        {value}
      </div>
    </div>
  );
}

function RowMeter({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-28 text-xs text-black/55 truncate">{label}</div>
      <div className="flex-1 h-2 rounded-full bg-white/70 overflow-hidden border border-white/70">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[color:var(--bbva-blue)] to-[color:var(--bbva-aqua)]"
          style={{ width: `${Math.min(100, value * 6)}%` }}
        />
      </div>
      <div className="w-8 text-right text-xs text-black/55">{value}</div>
    </div>
  );
}

type MentionSource = { name: string; url?: string };
type MentionGroup = {
  key: string;
  title: string;
  text?: string;
  geo?: string;
  actor?: string;
  sentiment?: string;
  published_at?: string | null;
  collected_at?: string | null;
  sources: MentionSource[];
  count: number;
};

function MentionCard({ item, index }: { item: MentionGroup; index: number }) {
  const sentimentTone = getSentimentTone(item.sentiment);
  const sanitizedTitle = cleanText(item.title) || "Sin título";
  const sanitizedText = cleanText(item.text);
  const displayDate = formatDate(item.published_at || item.collected_at);

  return (
    <article
      className="group relative overflow-hidden rounded-[22px] border border-white/70 bg-white/85 p-4 shadow-[0_16px_40px_rgba(7,33,70,0.12)] animate-rise"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms` }}
    >
      <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-[color:var(--bbva-aqua)] via-[color:var(--bbva-blue)] to-transparent opacity-70" />
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-black/55">
        <span className="inline-flex items-center gap-1 rounded-full border border-white/70 bg-white/80 px-2.5 py-1">
          <MapPin className="h-3.5 w-3.5 text-[color:var(--bbva-blue)]" />
          {item.geo || "Global"}
        </span>
        <span className="inline-flex items-center gap-1 rounded-full border border-white/70 bg-white/80 px-2.5 py-1">
          <Building2 className="h-3.5 w-3.5 text-[color:var(--bbva-blue)]" />
          {item.actor || "BBVA"}
        </span>
        <span className="inline-flex items-center gap-1 rounded-full border border-white/70 bg-white/80 px-2.5 py-1">
          <Calendar className="h-3.5 w-3.5 text-[color:var(--bbva-blue)]" />
          {displayDate}
        </span>
        <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 ${sentimentTone.className}`}>
          {sentimentTone.icon}
          {sentimentTone.label}
        </span>
        {item.sources.length > 1 && (
          <span className="inline-flex items-center gap-1 rounded-full border border-white/70 bg-white/80 px-2.5 py-1 text-[11px] text-black/60">
            {item.sources.length} fuentes
          </span>
        )}
      </div>
      <div className="mt-3 text-base font-display font-semibold text-[color:var(--bbva-ink)]">
        {sanitizedTitle}
      </div>
      {sanitizedText && (
        <div
          className="mt-2 text-sm text-black/70"
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
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-black/45">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-[0.16em] text-black/40">
            Fuentes
          </span>
          {item.sources.map((src) =>
            src.url ? (
              <a
                key={src.name}
                href={src.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-full border border-white/70 bg-white/80 px-2.5 py-1 text-[11px] text-[color:var(--bbva-blue)] hover:text-[color:var(--bbva-navy)] transition"
              >
                {src.name}
                <ArrowUpRight className="h-3 w-3" />
              </a>
            ) : (
              <span
                key={src.name}
                className="inline-flex items-center gap-1 rounded-full border border-white/70 bg-white/80 px-2.5 py-1 text-[11px] text-[color:var(--bbva-blue)]"
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
            className="inline-flex items-center gap-1 text-[color:var(--bbva-blue)] hover:text-[color:var(--bbva-navy)] transition"
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

function groupMentions(items: ReputationItem[]) {
  const map = new Map<string, MentionGroup>();

  for (const item of items) {
    const title = cleanText(item.title || "");
    const text = cleanText(item.text || "");
    const base =
      title || text || item.url || String(item.id ?? "sin-titulo");
    const key = [
      normalizeKey(base),
      item.geo || "",
      item.actor || "",
    ].join("|");

    if (!map.has(key)) {
      map.set(key, {
        key,
        title: title || text || "Sin título",
        text: text || undefined,
        geo: item.geo || undefined,
        actor: item.actor || undefined,
        sentiment: item.sentiment || undefined,
        published_at: item.published_at || null,
        collected_at: item.collected_at || null,
        sources: [],
        count: 0,
      });
    }

    const group = map.get(key);
    if (!group) continue;

    group.count += 1;

    const candidateDate = item.published_at || item.collected_at || "";
    const currentDate = group.published_at || group.collected_at || "";
    if (candidateDate && candidateDate > currentDate) {
      group.published_at = item.published_at || group.published_at;
      group.collected_at = item.collected_at || group.collected_at;
    }

    if (text && (!group.text || text.length > group.text.length)) {
      group.text = text;
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

function isBbvaName(name: string) {
  return name.toLowerCase().includes("bbva");
}

function isBbvaItem(item: ReputationItem) {
  if (item.actor) return isBbvaName(item.actor);
  const haystack = `${item.title ?? ""} ${item.text ?? ""}`.toLowerCase();
  return haystack.includes("bbva");
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
) {
  const restrictActor =
    selectedActor !== "all" && !isBbvaName(selectedActor);
  const normalizedActor = selectedActor.toLowerCase();
  const map = new Map<
    string,
    {
      bbvaScore: number;
      bbvaCount: number;
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
        bbvaScore: 0,
        bbvaCount: 0,
        actorScore: 0,
        actorCount: 0,
      });
    }
    const entry = map.get(date);
    if (!entry) continue;

    if (isBbvaItem(item)) {
      entry.bbvaScore += score;
      entry.bbvaCount += 1;
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

  return Array.from(map.entries())
    .map(([date, entry]) => ({
      date,
      bbva: entry.bbvaCount ? entry.bbvaScore / entry.bbvaCount : null,
      actor: entry.actorCount
        ? entry.actorScore / entry.actorCount
        : null,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

function SentimentChart({
  data,
  bbvaLabel,
  actorLabel,
}: {
  data: { date: string; bbva: number | null; actor: number | null }[];
  bbvaLabel: string;
  actorLabel: string;
}) {
  const tooltipFormatter: Formatter<ValueType, string | number> = (
    value,
    name,
  ) => {
    if (typeof value === "number") {
      return value.toFixed(2);
    }
    return value ?? "";
  };

  if (!data.length) {
    return (
      <div className="h-full grid place-items-center text-sm text-black/45">
        No hay datos para el periodo seleccionado.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid stroke="rgba(7,33,70,0.08)" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(d: string) => d.slice(5)}
          fontSize={11}
        />
        <YAxis domain={[-1, 1]} fontSize={11} />
        <Tooltip
          formatter={tooltipFormatter}
          labelFormatter={(label) => `Fecha ${String(label ?? "")}`}
          contentStyle={{
            borderRadius: 16,
            border: "1px solid rgba(7,33,70,0.08)",
            boxShadow: "0 10px 30px rgba(7,33,70,0.12)",
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="bbva"
          name={bbvaLabel}
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
