"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Calendar,
  Clipboard,
  Globe2,
  Loader2,
  Newspaper,
  Sparkles,
  TrendingDown,
  Users2,
} from "lucide-react";
import { Shell } from "@/components/Shell";
import { apiGet, apiGetCached } from "@/lib/api";
import {
  INGEST_SUCCESS_EVENT,
  PROFILE_CHANGED_EVENT,
  SETTINGS_CHANGED_EVENT,
  type IngestSuccessDetail,
} from "@/lib/events";
import type { MarketInsightsResponse, ReputationMeta } from "@/lib/types";

function toDateInput(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function fmtPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "0.0%";
  return `${(value * 100).toFixed(1)}%`;
}

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "n/d";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "n/d";
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function compactText(value: string | null | undefined): string {
  return (value ?? "").trim().split(/\s+/).filter(Boolean).join(" ");
}

function buildOpinionComment(title: string | undefined, excerpt: string | undefined): string {
  const cleanTitle = compactText(title);
  const cleanExcerpt = compactText(excerpt);
  if (cleanTitle && cleanExcerpt) {
    return cleanTitle.toLowerCase() === cleanExcerpt.toLowerCase()
      ? cleanTitle
      : `${cleanTitle} ${cleanExcerpt}`;
  }
  return cleanTitle || cleanExcerpt;
}

export function MarketInsightsView() {
  const today = useMemo(() => new Date(), []);
  const defaultTo = useMemo(() => toDateInput(today), [today]);
  const defaultFrom = useMemo(() => {
    const d = new Date(today);
    d.setDate(d.getDate() - 29);
    return toDateInput(d);
  }, [today]);

  const [fromDate, setFromDate] = useState(defaultFrom);
  const [toDate, setToDate] = useState(defaultTo);
  const [geo, setGeo] = useState("all");
  const [metaGeos, setMetaGeos] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [insights, setInsights] = useState<MarketInsightsResponse | null>(null);
  const [profileRefresh, setProfileRefresh] = useState(0);
  const [reputationRefresh, setReputationRefresh] = useState(0);
  const ingestRefreshTimersRef = useRef<number[]>([]);

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
    window.addEventListener(SETTINGS_CHANGED_EVENT, handler as EventListener);
    return () => {
      window.removeEventListener(PROFILE_CHANGED_EVENT, handler as EventListener);
      window.removeEventListener(SETTINGS_CHANGED_EVENT, handler as EventListener);
    };
  }, []);

  useEffect(() => {
    let alive = true;
    apiGetCached<ReputationMeta>("/reputation/meta", {
      ttlMs: 60000,
      force: profileRefresh > 0 || reputationRefresh > 0,
    })
      .then((meta) => {
        if (!alive) return;
        const geos = (meta.geos ?? []).filter(Boolean);
        setMetaGeos(geos.sort((a, b) => a.localeCompare(b)));
      })
      .catch(() => {
        if (!alive) return;
        setMetaGeos([]);
      });
    return () => {
      alive = false;
    };
  }, [profileRefresh, reputationRefresh]);

  const loadInsights = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    if (geo !== "all") params.set("geo", geo);

    try {
      const doc = await apiGet<MarketInsightsResponse>(
        `/reputation/markets/insights?${params.toString()}`,
      );
      setInsights(doc);
    } catch (err) {
      setInsights(null);
      setError(err instanceof Error ? err.message : "No se pudo cargar la vista de markets");
    } finally {
      setLoading(false);
    }
  }, [fromDate, toDate, geo]);

  useEffect(() => {
    void loadInsights();
  }, [loadInsights, reputationRefresh]);

  const headerSubtitle =
    "Inteligencia de mercado lista para acción: voces insistentes y respuestas oficiales. Solo actor principal.";
  const responseTotals = insights?.responses?.totals;
  const repeatedReplies = insights?.responses?.repeated_replies ?? [];
  const actorReplies = insights?.responses?.actor_breakdown ?? [];

  return (
    <Shell>
      <section className="relative overflow-hidden rounded-[28px] border border-[color:var(--border-60)] bg-[color:var(--panel-strong)] p-6 shadow-[var(--shadow-lg)] animate-rise">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-24 -right-10 h-48 w-48 rounded-full bg-[color:var(--aqua)]/15 blur-3xl" />
          <div className="absolute -bottom-16 left-10 h-40 w-40 rounded-full bg-[color:var(--blue)]/10 blur-3xl" />
        </div>
        <div className="relative">
          <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-[color:var(--blue)] shadow-sm">
            <Newspaper className="h-3.5 w-3.5" />
            Markets Intelligence
          </div>
          <h1 className="mt-4 text-3xl sm:text-4xl font-display font-semibold text-[color:var(--ink)]">
            Wow Radar de mercado
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-[color:var(--text-60)]">{headerSubtitle}</p>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-[color:var(--text-55)]">
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Calendar className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Rango: {fromDate} → {toDate}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Globe2 className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Geografía: {geo === "all" ? "Todas" : geo}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Sparkles className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Comparativas: desactivadas
            </span>
          </div>
        </div>
      </section>

      <section className="mt-4 rounded-[24px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-4 shadow-[var(--shadow-md)]">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <Field label="Desde">
            <input
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
              className="w-full rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--ink)] outline-none focus:border-[color:var(--aqua)]"
            />
          </Field>
          <Field label="Hasta">
            <input
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
              className="w-full rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--ink)] outline-none focus:border-[color:var(--aqua)]"
            />
          </Field>
          <Field label="Geografía">
            <select
              value={geo}
              onChange={(event) => setGeo(event.target.value)}
              className="w-full rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--ink)] outline-none focus:border-[color:var(--aqua)]"
            >
              <option value="all">Todas</option>
              {metaGeos.map((entry) => (
                <option key={entry} value={entry}>
                  {entry}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Última actualización">
            <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-60)]">
              {fmtDateTime(insights?.generated_at)}
            </div>
          </Field>
        </div>
      </section>

      {error && (
        <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {loading && (
        <div className="mt-4 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--panel)] p-4 text-sm text-[color:var(--text-60)]">
          <span className="inline-flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Construyendo insights de mercado...
          </span>
        </div>
      )}

      {!!insights && !loading && (
        <>
          <section className="mt-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
            <KpiCard
              icon={<Newspaper className="h-4 w-4" />}
              label="Menciones"
              value={String(insights.kpis.total_mentions)}
              detail={`${insights.principal_actor} · actor principal`}
            />
            <KpiCard
              icon={<TrendingDown className="h-4 w-4" />}
              label="Negativas"
              value={fmtPercent(insights.kpis.negative_ratio)}
              detail={`${insights.kpis.negative_mentions} menciones`}
            />
            <KpiCard
              icon={<Users2 className="h-4 w-4" />}
              label="Autores recurrentes"
              value={String(insights.kpis.recurring_authors)}
              detail={`${insights.kpis.unique_authors} autores únicos`}
            />
            <KpiCard
              icon={<Sparkles className="h-4 w-4" />}
              label="Score medio"
              value={
                insights.kpis.average_sentiment_score != null
                  ? insights.kpis.average_sentiment_score.toFixed(2)
                  : "n/d"
              }
              detail="Sentiment score agregado"
            />
            <KpiCard
              icon={<Clipboard className="h-4 w-4" />}
              label="Contestadas"
              value={
                responseTotals
                  ? fmtPercent(responseTotals.answered_ratio)
                  : "0.0%"
              }
              detail={
                responseTotals
                  ? `${responseTotals.answered_total}/${responseTotals.opinions_total} opiniones`
                  : "Sin respuestas detectadas"
              }
            />
          </section>

          <section className="mt-4 grid grid-cols-1 xl:grid-cols-[1.15fr_1fr] gap-4">
            <article className="rounded-[24px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)]">
              <h2 className="text-sm font-semibold tracking-[0.2em] uppercase text-[color:var(--blue)]">
                Respuestas oficiales
              </h2>
              <p className="mt-2 text-xs text-[color:var(--text-55)]">
                Opiniones contestadas por el mercado en el periodo seleccionado, agrupadas por similitud (&gt;=70%).
              </p>
              <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2">
                <MetricPill
                  label="Positivas contestadas"
                  value={String(responseTotals?.answered_positive ?? 0)}
                />
                <MetricPill
                  label="Neutrales contestadas"
                  value={String(responseTotals?.answered_neutral ?? 0)}
                />
                <MetricPill
                  label="Negativas contestadas"
                  value={String(responseTotals?.answered_negative ?? 0)}
                />
              </div>
              <div className="mt-4 space-y-3">
                {repeatedReplies.length === 0 && (
                  <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                    No se detectan respuestas generales.
                  </div>
                )}
                {repeatedReplies.slice(0, 5).map((entry) => (
                  <div
                    key={`${entry.reply_text}-${entry.count}`}
                    className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-55)]">
                        {entry.count > 1
                          ? `Respuesta general · ${entry.count} comentarios`
                          : "Respuesta única · 1 comentario"}
                      </div>
                      <div className="text-xs text-[color:var(--text-55)]">
                        {entry.actors.slice(0, 2).map((actor) => actor.actor).join(" · ")}
                      </div>
                    </div>
                    <div className="mt-1 text-sm text-[color:var(--ink)]">
                      {entry.reply_text}
                    </div>
                  </div>
                ))}
              </div>
            </article>

            <article className="rounded-[24px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)]">
              <h2 className="text-sm font-semibold tracking-[0.2em] uppercase text-[color:var(--blue)]">
                Quién contesta
              </h2>
              <p className="mt-2 text-xs text-[color:var(--text-55)]">
                Distribución por actor principal/secundario.
              </p>
              <div className="mt-4 space-y-2">
                {actorReplies.length === 0 && (
                  <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                    Sin actores con respuestas detectadas.
                  </div>
                )}
                {actorReplies.slice(0, 8).map((actor) => (
                  <div
                    key={`${actor.actor}-${actor.actor_type}`}
                    className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm text-[color:var(--ink)]">{actor.actor}</div>
                      <span className="rounded-full border border-[color:var(--border-60)] px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-55)]">
                        {actor.actor_type}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-[color:var(--text-55)]">
                      Contestadas: {actor.answered} · +{actor.answered_positive} / ={actor.answered_neutral} / -{actor.answered_negative}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <section className="mt-4">
            <article className="rounded-[24px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)]">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold tracking-[0.2em] uppercase text-[color:var(--blue)]">
                  Voces insistentes
                </h2>
                <span className="text-xs text-[color:var(--text-55)]">
                  Top 10
                </span>
              </div>
              <p className="mt-2 text-xs text-[color:var(--text-55)]">
                Usuarios con múltiples opiniones en el periodo seleccionado.
              </p>
              <div className="mt-4 space-y-3">
                {insights.recurring_authors.length === 0 && (
                  <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2 text-sm text-[color:var(--text-55)]">
                    No se detectan autores con 2 o más opiniones en este corte.
                  </div>
                )}
                {insights.recurring_authors.map((author) => (
                  <details
                    key={author.author}
                    className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2"
                  >
                    <summary className="cursor-pointer list-none">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-semibold text-[color:var(--ink)]">
                          {author.author}
                        </div>
                        <span className="rounded-full border border-[color:var(--border-60)] px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-55)]">
                          {author.opinions_count} opiniones
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-[color:var(--text-55)]">
                        Última mención: {fmtDateTime(author.last_seen)}
                      </div>
                    </summary>
                    <ul className="mt-3 space-y-2">
                      {author.opinions.map((opinion) => {
                        const opinionComment = buildOpinionComment(opinion.title, opinion.excerpt);
                        const opinionAuthor = compactText(opinion.author || author.author);
                        return (
                          <li
                            key={opinion.id}
                            className="rounded-lg border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2"
                          >
                            <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-55)]">
                              <span>{opinion.source}</span>
                              <span>{opinion.geo}</span>
                              <span>{opinion.sentiment}</span>
                              <span>{fmtDateTime(opinion.published_at)}</span>
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[color:var(--text-55)]">
                              <span className="rounded-full border border-[color:var(--border-60)] px-2 py-0.5">
                                Autor: {opinionAuthor || "Autor sin nombre"}
                              </span>
                              <span className="rounded-full border border-[color:var(--border-60)] px-2 py-0.5">
                                ID: {opinion.id}
                              </span>
                            </div>
                            <div className="mt-2 rounded-lg border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2">
                              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-55)]">
                                Comentario
                              </div>
                              <div className="mt-1 text-sm text-[color:var(--ink)]">
                                {opinionComment || "Sin texto de comentario"}
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                ))}
              </div>
            </article>
          </section>

        </>
      )}
    </Shell>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-60)]">
        {label}
      </span>
      {children}
    </label>
  );
}

function KpiCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="rounded-[22px] border border-[color:var(--border-60)] bg-[color:var(--panel)] px-4 py-4 shadow-[var(--shadow-md)]">
      <div className="flex items-center justify-between gap-3 text-[color:var(--text-55)]">
        <span className="text-xs uppercase tracking-[0.18em]">{label}</span>
        <span className="text-[color:var(--blue)]">{icon}</span>
      </div>
      <div className="mt-2 text-3xl font-display font-semibold text-[color:var(--ink)]">{value}</div>
      <div className="mt-1 text-xs text-[color:var(--text-60)]">{detail}</div>
    </article>
  );
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-55)]">
        {label}
      </div>
      <div className="mt-1 text-xl font-display font-semibold text-[color:var(--ink)]">{value}</div>
    </div>
  );
}
