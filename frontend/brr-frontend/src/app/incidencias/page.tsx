"use client";

/**
 * Vista de incidencias con filtros en cliente.
 */

import { useEffect, useMemo, useState } from "react";
import { Calendar, Filter, Loader2, Search, Sparkles } from "lucide-react";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import { EvolutionChart } from "@/components/EvolutionChart";
import type { EvolutionPoint, Severity } from "@/lib/types";

const EVOLUTION_DAYS = 90;

type Incident = {
  global_id: string;
  title: string;
  status: string;
  severity: Severity | string;
  opened_at?: string | null;
  closed_at?: string | null;
  product?: string | null;
  feature?: string | null;
};

function chipSeverity(sev: string) {
  /** Devuelve clases CSS segun severidad. */
  const s = (sev ?? "UNKNOWN").toUpperCase();
  if (s === "CRITICAL") return "bg-rose-50 text-rose-700 border-rose-200";
  if (s === "HIGH") return "bg-amber-50 text-amber-700 border-amber-200";
  if (s === "MEDIUM") return "bg-blue-50 text-blue-700 border-blue-200";
  if (s === "LOW") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  return "bg-slate-50 text-slate-600 border-slate-200";
}

function chipStatus(st: string) {
  /** Devuelve clases CSS segun estado. */
  const s = (st ?? "").toUpperCase();
  if (s === "OPEN") return "bg-sky-50 text-sky-700 border-sky-200";
  if (s === "IN_PROGRESS") return "bg-purple-50 text-purple-700 border-purple-200";
  if (s === "CLOSED") return "bg-slate-50 text-slate-600 border-slate-200";
  return "bg-slate-50 text-slate-600 border-slate-200";
}

export default function IncidenciasPage() {
  /** Lista completa de incidencias. */
  const [items, setItems] = useState<Incident[]>([]);
  const [itemsLoading, setItemsLoading] = useState(true);
  /** Mensaje de error si falla la API. */
  const [error, setError] = useState<string | null>(null);
  const [evolution, setEvolution] = useState<EvolutionPoint[]>([]);
  const [evolutionLoading, setEvolutionLoading] = useState(true);
  const [evolutionError, setEvolutionError] = useState<string | null>(null);

  /** Filtros de busqueda. */
  const [q, setQ] = useState("");
  const [sev, setSev] = useState<string>("ALL");
  const [st, setSt] = useState<string>("ALL");

  useEffect(() => {
    let alive = true;
    setItemsLoading(true);
    apiGet<{ items: Incident[] }>("/incidents?limit=5000")
      .then((r) => {
        if (!alive) return;
        setItems(r.items);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e));
      })
      .finally(() => {
        if (!alive) return;
        setItemsLoading(false);
      });

    apiGet<{ days: number; series: EvolutionPoint[] }>(`/evolution?days=${EVOLUTION_DAYS}`)
      .then((r) => {
        if (!alive) return;
        setEvolution(r.series ?? []);
      })
      .catch((e) => {
        if (!alive) return;
        setEvolutionError(String(e));
      })
      .finally(() => {
        if (!alive) return;
        setEvolutionLoading(false);
      });

    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return items.filter((it) => {
      const okQ =
        !qq ||
        it.global_id.toLowerCase().includes(qq) ||
        (it.title ?? "").toLowerCase().includes(qq) ||
        (it.product ?? "").toLowerCase().includes(qq) ||
        (it.feature ?? "").toLowerCase().includes(qq);

      const okSev = sev === "ALL" || (it.severity ?? "").toString().toUpperCase() === sev;
      const okSt = st === "ALL" || (it.status ?? "").toString().toUpperCase() === st;

      return okQ && okSev && okSt;
    });
  }, [items, q, sev, st]);

  const activeFilters =
    (q ? 1 : 0) + (sev !== "ALL" ? 1 : 0) + (st !== "ALL" ? 1 : 0);
  const hasActiveFilters = activeFilters > 0;
  const errorMessage = error || evolutionError;
  const filteredEvolution = useMemo(
    () => buildEvolutionSeries(filtered, EVOLUTION_DAYS),
    [filtered],
  );
  const chartData = useMemo(() => {
    if (hasActiveFilters) {
      return filteredEvolution;
    }
    return evolution.length ? evolution : filteredEvolution;
  }, [hasActiveFilters, evolution, filteredEvolution]);
  const chartLoading = evolutionLoading && !hasActiveFilters;

  return (
    <Shell>
      <section className="relative overflow-hidden rounded-[28px] border border-white/60 bg-[color:var(--panel-strong)] p-6 shadow-[0_30px_70px_rgba(7,33,70,0.12)] animate-rise">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-24 -right-10 h-48 w-48 rounded-full bg-[color:var(--aqua)]/15 blur-3xl" />
          <div className="absolute -bottom-16 left-10 h-40 w-40 rounded-full bg-[color:var(--blue)]/10 blur-3xl" />
        </div>
        <div className="relative">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/60 bg-white/70 px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-[color:var(--blue)] shadow-sm">
            <Sparkles className="h-3.5 w-3.5" />
            Incidencias críticas
          </div>
          <h1 className="mt-4 text-3xl sm:text-4xl font-display font-semibold text-[color:var(--ink)]">
            Incidencias
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-black/60">
            Listado consolidado desde los distintos orígenes para seguimiento y
            priorización.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-black/55">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              <Calendar className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Total cargadas:{" "}
              {itemsLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[color:var(--blue)]" />
              ) : (
                items.length
              )}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              <Search className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Mostrando:{" "}
              {itemsLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[color:var(--blue)]" />
              ) : (
                filtered.length
              )}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              <Filter className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Filtros activos: {activeFilters}
            </span>
          </div>
        </div>
      </section>

      {errorMessage && (
        <div className="mt-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {errorMessage}
        </div>
      )}

      {/* Filtros */}
      <div className="mt-6 rounded-[26px] border border-white/60 bg-[color:var(--panel)] p-5 shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl animate-rise" style={{ animationDelay: "120ms" }}>
        <div className="grid grid-cols-1 md:grid-cols-[1fr_180px_180px] gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-black/50 mb-2">
              Buscar
            </div>
            <div className="flex items-center gap-2 rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)]">
              <Search className="h-4 w-4 text-[color:var(--blue)]" />
              <input
                className="w-full bg-transparent outline-none"
                placeholder="ID, título, producto, funcionalidad…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-black/50 mb-2">
              Criticidad
            </div>
            <select
              className="w-full rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
              value={sev}
              onChange={(e) => setSev(e.target.value)}
            >
              <option value="ALL">Todas</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
              <option value="UNKNOWN">UNKNOWN</option>
            </select>
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-black/50 mb-2">
              Estado
            </div>
            <select
              className="w-full rounded-2xl border border-white/60 bg-white/80 px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_rgba(255,255,255,0.6)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
              value={st}
              onChange={(e) => setSt(e.target.value)}
            >
              <option value="ALL">Todos</option>
              <option value="OPEN">OPEN</option>
              <option value="IN_PROGRESS">IN_PROGRESS</option>
              <option value="CLOSED">CLOSED</option>
            </select>
          </div>
        </div>
      </div>

      {/* Evolucion */}
      <div className="mt-6 rounded-[26px] border border-white/60 bg-[color:var(--panel)] p-5 shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl animate-rise" style={{ animationDelay: "150ms" }}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
            EVOLUCIÓN TEMPORAL
          </h2>
          <span className="text-xs text-black/50">
            Últimos {EVOLUTION_DAYS} días{hasActiveFilters ? " · filtros activos" : ""}
          </span>
        </div>
        <div className="mt-4 h-72 min-h-[260px]">
          {chartLoading ? (
            <div className="h-full rounded-[22px] border border-white/60 bg-white/70 animate-pulse" />
          ) : chartData.length ? (
            <EvolutionChart data={chartData} />
          ) : (
            <div className="h-full grid place-items-center text-sm text-black/45">
              Sin datos para el periodo seleccionado.
            </div>
          )}
        </div>
      </div>

      {/* Tabla */}
      <div className="mt-6 rounded-[26px] border border-white/60 bg-[color:var(--panel)] shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl overflow-hidden animate-rise" style={{ animationDelay: "180ms" }}>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead
              className="sticky top-0 bg-white/80 backdrop-blur border-b"
              style={{ borderColor: "rgba(7,33,70,0.08)" }}
            >
              <tr className="text-left text-[11px] uppercase tracking-[0.2em] text-black/45">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Título</th>
                <th className="px-4 py-3">Estado</th>
                <th className="px-4 py-3">Criticidad</th>
                <th className="px-4 py-3">Producto</th>
                <th className="px-4 py-3">Funcionalidad</th>
                <th className="px-4 py-3">Abierta</th>
              </tr>
            </thead>

            <tbody>
              {itemsLoading ? (
                <SkeletonTableRows columns={7} rows={5} />
              ) : (
                filtered.map((it, idx) => (
                  <tr
                    key={it.global_id}
                    className={idx % 2 === 0 ? "bg-white/70" : "bg-white/40"}
                    style={{ borderTop: "1px solid rgba(7,33,70,0.08)" }}
                  >
                    <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">
                      {it.global_id}
                    </td>
                    <td className="px-4 py-3 min-w-[360px]">
                      <div className="font-semibold text-[color:var(--ink)]">
                        {it.title}
                      </div>
                      <div className="text-xs text-black/55">
                        {it.product ?? "—"} · {it.feature ?? "—"}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${chipStatus(it.status)}`}>
                        {it.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${chipSeverity(String(it.severity))}`}>
                        {String(it.severity)}
                      </span>
                    </td>
                    <td className="px-4 py-3">{it.product ?? "—"}</td>
                    <td className="px-4 py-3">{it.feature ?? "—"}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {it.opened_at ?? "—"}
                    </td>
                  </tr>
                ))
              )}

              {!itemsLoading && filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-black/55">
                    No hay incidencias para mostrar con los filtros actuales.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}

function SkeletonTableRows({ columns, rows }: { columns: number; rows: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <tr key={rowIdx} className="border-t border-white/60 animate-pulse">
          {Array.from({ length: columns }).map((_, colIdx) => (
            <td key={colIdx} className="px-4 py-3">
              <div className="h-3 w-full max-w-[120px] rounded-full bg-white/70 border border-white/60" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

function buildEvolutionSeries(items: Incident[], days: number): EvolutionPoint[] {
  if (!items.length || days <= 0) return [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setDate(start.getDate() - (days - 1));

  const normalized = items
    .map((item) => ({
      opened: toDateOnly(item.opened_at),
      closed: toDateOnly(item.closed_at),
    }))
    .filter((row) => row.opened);

  const series: EvolutionPoint[] = [];
  for (let i = 0; i < days; i += 1) {
    const day = new Date(start);
    day.setDate(start.getDate() + i);
    const key = toDateKey(day);

    let open = 0;
    let fresh = 0;
    let closed = 0;

    for (const row of normalized) {
      const opened = row.opened!;
      const closedAt = row.closed;
      if (toDateKey(opened) === key) {
        fresh += 1;
      }
      if (closedAt && toDateKey(closedAt) === key) {
        closed += 1;
      }
      if (opened <= day && (!closedAt || closedAt > day)) {
        open += 1;
      }
    }

    series.push({ date: key, open, new: fresh, closed });
  }

  return series;
}

function toDateOnly(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  date.setHours(0, 0, 0, 0);
  return date;
}

function toDateKey(date: Date) {
  return date.toISOString().slice(0, 10);
}
