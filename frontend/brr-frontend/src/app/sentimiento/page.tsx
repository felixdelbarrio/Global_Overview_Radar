"use client";

/**
 * Vista de sentimiento historico por pais / periodo / fuente.
 */

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Formatter } from "recharts/types/component/DefaultTooltipContent";
import type { ValueType } from "recharts/types/component/DefaultTooltipContent";
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
    d.setDate(d.getDate() - 30);
    return toDateInput(d);
  }, [today]);

  const [items, setItems] = useState<ReputationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [fromDate, setFromDate] = useState(defaultFrom);
  const [toDate, setToDate] = useState(defaultTo);
  const [sentiment, setSentiment] = useState<SentimentFilter>("all");
  const [entity, setEntity] = useState("bbva");
  const [geo, setGeo] = useState("all");
  const [competitor, setCompetitor] = useState("all");
  const [sources, setSources] = useState<string[]>([]);

  useEffect(() => {
    if (entity === "bbva") {
      setCompetitor("all");
      return;
    }
    if (entity === "competencia" && competitor === "BBVA") {
      setCompetitor("all");
    }
  }, [entity, competitor]);

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
    if (competitor !== "all") params.set("competitor", competitor);
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
  }, [fromDate, toDate, sentiment, entity, geo, competitor, sources]);

  const sourcesOptions = useMemo(() => unique(items.map((i) => i.source)), [items]);
  const geoOptions = useMemo(() => unique(items.map((i) => i.geo).filter(Boolean) as string[]), [items]);
  const competitorOptions = useMemo(() => {
    const values = unique(
      items.map((i) => i.competitor).filter(Boolean) as string[],
    );
    if (entity === "bbva") return ["BBVA"];
    if (entity === "competencia") return values.filter((v) => v !== "BBVA");
    return values;
  }, [items, entity]);

  const sentimentSummary = useMemo(() => summarize(items), [items]);
  const geoSummary = useMemo(() => summarizeByGeo(items), [items]);
  const topSources = useMemo(() => topCounts(items, (i) => i.source), [items]);
  const topCompetitors = useMemo(
    () => topCounts(items, (i) => i.competitor || "Sin competidor"),
    [items],
  );
  const sentimentSeries = useMemo(() => buildSentimentSeries(items), [items]);

  return (
    <Shell>
      <h1 className="text-2xl font-semibold text-[color:var(--bbva-navy)]">
        Sentimiento histórico
      </h1>
      <p className="text-sm text-black/60 mt-1">
        Analiza el sentimiento por país, periodo y fuente de datos.
      </p>

      {error && (
        <div className="mt-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-4">
        <section className="rounded-2xl bg-white border border-black/5 p-4 shadow-sm">
          <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
            FILTROS PRINCIPALES
          </div>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <FilterField label="Desde">
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm"
              />
            </FilterField>
            <FilterField label="Hasta">
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm"
              />
            </FilterField>
            <FilterField label="Sentimiento">
              <select
                value={sentiment}
                onChange={(e) => setSentiment(e.target.value as SentimentFilter)}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm"
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
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm"
              >
                <option value="bbva">BBVA</option>
                <option value="competencia">Competencia</option>
                <option value="all">Todas</option>
              </select>
            </FilterField>
            <FilterField label="País">
              <select
                value={geo}
                onChange={(e) => setGeo(e.target.value)}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm"
              >
                <option value="all">Todos</option>
                {geoOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Competidor">
              <select
                value={competitor}
                onChange={(e) => setCompetitor(e.target.value)}
                disabled={entity === "bbva"}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm"
              >
                <option value="all">Todos</option>
                {competitorOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </FilterField>
          </div>

          <div className="mt-4">
            <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
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
                      "rounded-full px-3 py-1.5 text-xs border transition " +
                      (active
                        ? "bg-[color:var(--bbva-blue)] text-white border-transparent"
                        : "bg-white text-[color:var(--bbva-navy)] border-black/10")
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

        <section className="rounded-2xl bg-white border border-black/5 p-4 shadow-sm">
          <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
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
            <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
              TOP FUENTES
            </div>
            <div className="mt-2 space-y-2">
              {topSources.map((row) => (
                <RowMeter key={row.key} label={row.key} value={row.count} />
              ))}
            </div>
          </div>
          <div className="mt-4">
            <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
              TOP COMPETIDORES
            </div>
            <div className="mt-2 space-y-2">
              {topCompetitors.map((row) => (
                <RowMeter key={row.key} label={row.key} value={row.count} />
              ))}
            </div>
          </div>
        </section>
      </div>

      <section className="mt-6 rounded-2xl bg-white border border-black/5 p-4 shadow-sm">
        <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
          SENTIMIENTO POR PAÍS
        </div>
        <div className="mt-3 overflow-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-black/50">
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
                <tr key={row.geo} className="border-t border-black/5">
                  <td className="py-2 pr-4 font-medium text-[color:var(--bbva-navy)]">
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

      <section className="mt-6 rounded-2xl bg-white border border-black/5 p-4 shadow-sm">
        <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
          EVOLUCIÓN DE REPUTACIÓN
        </div>
        <div className="mt-3 h-72 min-h-[240px]">
          <SentimentChart data={sentimentSeries} />
        </div>
      </section>

      <section className="mt-6 rounded-2xl bg-white border border-black/5 p-4 shadow-sm">
        <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
          ÚLTIMAS MENCIONES
        </div>
        <div className="mt-3 space-y-3">
          {loading && (
            <div className="text-sm text-black/50">Cargando sentimiento…</div>
          )}
          {!loading &&
            items.slice(0, 20).map((item) => (
              <MentionCard key={`${item.source}-${item.id}`} item={item} />
            ))}
          {!loading && !items.length && (
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
    <label className="text-xs text-black/60">
      <span className="block mb-1">{label}</span>
      {children}
    </label>
  );
}

function SummaryCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-black/5 bg-[color:var(--panel)] px-3 py-2">
      <div className="text-xs text-black/45">{label}</div>
      <div className="text-lg font-semibold text-[color:var(--bbva-navy)]">
        {value}
      </div>
    </div>
  );
}

function RowMeter({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-28 text-xs text-black/55 truncate">{label}</div>
      <div className="flex-1 h-2 rounded-full bg-black/5 overflow-hidden">
        <div
          className="h-full rounded-full bg-[color:var(--bbva-blue)]"
          style={{ width: `${Math.min(100, value * 6)}%` }}
        />
      </div>
      <div className="w-8 text-right text-xs text-black/55">{value}</div>
    </div>
  );
}

function MentionCard({ item }: { item: ReputationItem }) {
  return (
    <div className="rounded-xl border border-black/5 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2 text-xs text-black/50">
        <span className="px-2 py-0.5 rounded-full bg-black/5">
          {item.source}
        </span>
        {item.geo && (
          <span className="px-2 py-0.5 rounded-full bg-black/5">
            {item.geo}
          </span>
        )}
        {item.competitor && (
          <span className="px-2 py-0.5 rounded-full bg-black/5">
            {item.competitor}
          </span>
        )}
        {item.sentiment && (
          <span className="px-2 py-0.5 rounded-full bg-black/5">
            {item.sentiment}
          </span>
        )}
      </div>
      <div className="mt-2 text-sm font-semibold text-[color:var(--bbva-navy)]">
        {item.title || "Sin título"}
      </div>
      {item.text && (
        <div className="mt-1 text-sm text-black/70">{item.text}</div>
      )}
      <div className="mt-2 text-xs text-black/45">
        {item.published_at || item.collected_at || "Sin fecha"}
      </div>
      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex text-xs text-[color:var(--bbva-blue)]"
        >
          Ver detalle →
        </a>
      )}
    </div>
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

function buildSentimentSeries(items: ReputationItem[]) {
  const map = new Map<string, { score: number; count: number }>();
  for (const item of items) {
    const rawDate = item.published_at || item.collected_at;
    if (!rawDate) continue;
    const date = rawDate.slice(0, 10);
    const score = Number(
      (item.signals as Record<string, unknown>)?.sentiment_score,
    );
    if (Number.isNaN(score)) continue;
    if (!map.has(date)) {
      map.set(date, { score: 0, count: 0 });
    }
    const entry = map.get(date);
    if (!entry) continue;
    entry.score += score;
    entry.count += 1;
  }

  return Array.from(map.entries())
    .map(([date, entry]) => ({
      date,
      avg_score: entry.count ? entry.score / entry.count : 0,
      count: entry.count,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

function SentimentChart({
  data,
}: {
  data: { date: string; avg_score: number; count: number }[];
}) {
  const tooltipFormatter: Formatter<ValueType, string | number> = (
    value,
    name,
  ) => {
    if (typeof value === "number") {
      return name === "avg_score" ? value.toFixed(2) : value;
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
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="date"
          tickFormatter={(d: string) => d.slice(5)}
          fontSize={11}
        />
        <YAxis domain={[-1, 1]} fontSize={11} />
        <Tooltip
          formatter={tooltipFormatter}
          labelFormatter={(label) => `Fecha ${String(label ?? "")}`}
        />
        <Line
          type="monotone"
          dataKey="avg_score"
          name="Score medio"
          stroke="#004481"
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
