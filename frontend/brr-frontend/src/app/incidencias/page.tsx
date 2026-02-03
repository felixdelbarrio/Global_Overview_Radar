"use client";

/**
 * Vista de incidencias con filtros en cliente.
 */

import { useEffect, useMemo, useState } from "react";
import { Calendar, Download, Filter, Loader2, Search, Sparkles } from "lucide-react";
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
  const today = useMemo(() => new Date(), []);
  const defaultTo = useMemo(() => toDateInput(today), [today]);
  const defaultFrom = useMemo(() => {
    const d = new Date(today);
    d.setDate(d.getDate() - (EVOLUTION_DAYS - 1));
    return toDateInput(d);
  }, [today]);
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
  const [fromDate, setFromDate] = useState(defaultFrom);
  const [toDate, setToDate] = useState(defaultTo);

  useEffect(() => {
    let alive = true;
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

  const range = useMemo(
    () => normalizeDateRange(fromDate, toDate),
    [fromDate, toDate],
  );
  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return items.filter((it) => {
      const itemDate = toDateOnly(it.opened_at ?? it.closed_at);
      const okDate =
        (!range.start || (itemDate && itemDate >= range.start)) &&
        (!range.end || (itemDate && itemDate <= range.end));
      const okQ =
        !qq ||
        it.global_id.toLowerCase().includes(qq) ||
        (it.title ?? "").toLowerCase().includes(qq) ||
        (it.product ?? "").toLowerCase().includes(qq) ||
        (it.feature ?? "").toLowerCase().includes(qq);

      const okSev = sev === "ALL" || (it.severity ?? "").toString().toUpperCase() === sev;
      const okSt = st === "ALL" || (it.status ?? "").toString().toUpperCase() === st;

      return okDate && okQ && okSev && okSt;
    });
  }, [items, q, sev, st, range]);

  const isDefaultRange = fromDate === defaultFrom && toDate === defaultTo;
  const activeFilters =
    (q ? 1 : 0) +
    (sev !== "ALL" ? 1 : 0) +
    (st !== "ALL" ? 1 : 0) +
    (!isDefaultRange ? 1 : 0);
  const hasActiveFilters = activeFilters > 0;
  const dateRangeLabel = isDefaultRange
    ? `Últimos ${EVOLUTION_DAYS} días`
    : `${range.start ? toDateKey(range.start) : "—"} → ${
        range.end ? toDateKey(range.end) : "—"
      }`;
  const errorMessage = error || evolutionError;
  const filteredEvolution = useMemo(
    () => buildEvolutionSeries(filtered, EVOLUTION_DAYS, fromDate, toDate),
    [filtered, fromDate, toDate],
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
      <section className="relative overflow-hidden rounded-[28px] border border-[color:var(--border-60)] bg-[color:var(--panel-strong)] p-6 shadow-[var(--shadow-lg)] animate-rise">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-24 -right-10 h-48 w-48 rounded-full bg-[color:var(--aqua)]/15 blur-3xl" />
          <div className="absolute -bottom-16 left-10 h-40 w-40 rounded-full bg-[color:var(--blue)]/10 blur-3xl" />
        </div>
        <div className="relative">
          <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-[color:var(--blue)] shadow-sm">
            <Sparkles className="h-3.5 w-3.5" />
            Incidencias críticas
          </div>
          <h1 className="mt-4 text-3xl sm:text-4xl font-display font-semibold text-[color:var(--ink)]">
            Incidencias
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[color:var(--text-60)]">
            Listado consolidado desde los distintos orígenes para seguimiento y
            priorización.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-[color:var(--text-55)]">
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Calendar className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Total cargadas:{" "}
              {itemsLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[color:var(--blue)]" />
              ) : (
                items.length
              )}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Search className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Mostrando:{" "}
              {itemsLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[color:var(--blue)]" />
              ) : (
                filtered.length
              )}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
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
      <div className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "120ms" }}>
        <div className="grid grid-cols-1 md:grid-cols-[1fr_180px_180px_180px_180px] gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-50)] mb-2">
              Buscar
            </div>
            <div className="flex items-center gap-2 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)]">
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
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-50)] mb-2">
              Criticidad
            </div>
            <select
              className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
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
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-50)] mb-2">
              Estado
            </div>
            <select
              className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
              value={st}
              onChange={(e) => setSt(e.target.value)}
            >
              <option value="ALL">Todos</option>
              <option value="OPEN">OPEN</option>
              <option value="IN_PROGRESS">IN_PROGRESS</option>
              <option value="CLOSED">CLOSED</option>
            </select>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-50)] mb-2">
              Desde
            </div>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
            />
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-50)] mb-2">
              Hasta
            </div>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none focus:border-[color:var(--aqua)]/60 focus:ring-2 focus:ring-[color:var(--aqua)]/30"
            />
          </div>
        </div>
      </div>

      {/* Evolucion */}
      <div className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "150ms" }}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
            EVOLUCIÓN TEMPORAL
          </h2>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-50)]">
            <span>
              {dateRangeLabel}
              {hasActiveFilters ? " · filtros activos" : ""}
            </span>
            <button
              type="button"
              onClick={() =>
                downloadEvolutionCsv(
                  chartData,
                  buildDownloadName("incidencias_evolucion", fromDate, toDate),
                )
              }
              disabled={chartLoading || chartData.length === 0}
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--brand-ink)] shadow-[var(--shadow-pill)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pill-hover)] disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-[var(--shadow-pill)]"
            >
              <Download className="h-3.5 w-3.5" />
              Descargar gráfico
            </button>
          </div>
        </div>
        <div className="mt-4 h-72 min-h-[260px]">
          {chartLoading ? (
            <div className="h-full rounded-[22px] border border-[color:var(--border-60)] bg-[color:var(--surface-70)] animate-pulse" />
          ) : chartData.length ? (
            <EvolutionChart data={chartData} />
          ) : (
            <div className="h-full grid place-items-center text-sm text-[color:var(--text-45)]">
              Sin datos para el periodo seleccionado.
            </div>
          )}
        </div>
      </div>

      {/* Tabla */}
      <div className="mt-6 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] shadow-[var(--shadow-md)] backdrop-blur-xl overflow-hidden animate-rise" style={{ animationDelay: "180ms" }}>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[color:var(--border-60)] px-5 py-4">
          <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
            RESULTADOS
          </div>
          <button
            type="button"
            onClick={() =>
              downloadIncidentsCsv(
                filtered,
                buildDownloadName("incidencias_resultados", fromDate, toDate),
              )
            }
            disabled={itemsLoading || filtered.length === 0}
            className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-80)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--brand-ink)] shadow-[var(--shadow-pill)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-pill-hover)] disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-[var(--shadow-pill)]"
          >
            <Download className="h-3.5 w-3.5" />
            Descargar resultados
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead
              className="sticky top-0 bg-[color:var(--surface-80)] backdrop-blur border-b"
              style={{ borderColor: "var(--border)" }}
            >
              <tr className="text-left text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-45)]">
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
                    className={idx % 2 === 0 ? "bg-[color:var(--surface-70)]" : "bg-[color:var(--surface-40)]"}
                    style={{ borderTop: "1px solid var(--border)" }}
                  >
                    <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">
                      {it.global_id}
                    </td>
                    <td className="px-4 py-3 min-w-[360px]">
                      <div className="font-semibold text-[color:var(--ink)]">
                        {it.title}
                      </div>
                      <div className="text-xs text-[color:var(--text-55)]">
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
                  <td colSpan={7} className="px-4 py-10 text-center text-[color:var(--text-55)]">
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
        <tr key={rowIdx} className="border-t border-[color:var(--border-60)] animate-pulse">
          {Array.from({ length: columns }).map((_, colIdx) => (
            <td key={colIdx} className="px-4 py-3">
              <div className="h-3 w-full max-w-[120px] rounded-full bg-[color:var(--surface-70)] border border-[color:var(--border-60)]" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

function buildEvolutionSeries(
  items: Incident[],
  days: number,
  fromDate?: string,
  toDate?: string,
): EvolutionPoint[] {
  if (!items.length || days <= 0) return [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const range = normalizeDateRange(fromDate, toDate, today, days);
  const start = range.start;
  const end = range.end;
  const totalDays =
    Math.max(0, Math.floor((end.getTime() - start.getTime()) / 86_400_000)) + 1;
  if (totalDays <= 0) return [];

  const normalized = items
    .map((item) => ({
      opened: toDateOnly(item.opened_at),
      closed: toDateOnly(item.closed_at),
    }))
    .filter((row) => row.opened);

  const series: EvolutionPoint[] = [];
  for (let i = 0; i < totalDays; i += 1) {
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

function toDateInput(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

function normalizeDateRange(
  fromDate?: string,
  toDate?: string,
  todayOverride?: Date,
  fallbackDays = EVOLUTION_DAYS,
) {
  const today = todayOverride ? new Date(todayOverride) : new Date();
  today.setHours(0, 0, 0, 0);
  let start = toDateOnly(fromDate);
  let end = toDateOnly(toDate);
  if (start && end && start > end) {
    const temp = start;
    start = end;
    end = temp;
  }
  if (!end) {
    end = today;
  }
  if (!start) {
    start = new Date(end);
    start.setDate(end.getDate() - (fallbackDays - 1));
  }
  return { start, end };
}

function buildDownloadName(prefix: string, fromDate?: string, toDate?: string) {
  const safePrefix = prefix.replace(/[^a-zA-Z0-9_-]+/g, "_");
  const range = normalizeDateRange(fromDate, toDate);
  const rangeFrom = range.start ? toDateKey(range.start) : "inicio";
  const rangeTo = range.end ? toDateKey(range.end) : "hoy";
  return `${safePrefix}_${rangeFrom}_${rangeTo}`;
}

function downloadEvolutionCsv(data: EvolutionPoint[], filename: string) {
  const headers = ["Fecha", "Abiertas", "Nuevas", "Cerradas"];
  const rows = data.map((row) => [row.date, row.open, row.new, row.closed]);
  downloadCsv(filename, headers, rows);
}

function downloadIncidentsCsv(items: Incident[], filename: string) {
  const headers = [
    "id",
    "titulo",
    "estado",
    "criticidad",
    "producto",
    "funcionalidad",
    "abierta",
    "cerrada",
  ];
  const rows = items.map((item) => [
    item.global_id,
    item.title ?? "",
    item.status ?? "",
    item.severity ?? "",
    item.product ?? "",
    item.feature ?? "",
    item.opened_at ?? "",
    item.closed_at ?? "",
  ]);
  downloadCsv(filename, headers, rows);
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
