"use client";

/**
 * Panel operativo (Ops Executive) con filtros, orden y paginacion.
 */

import { useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { Kpis } from "@/lib/types";
import {
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Zap,
  Archive,
  Hourglass,
  Search,
  Sparkles,
  Filter,
  Activity,
} from "lucide-react";

type Incident = {
  global_id: string;
  title: string;
  status: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
  opened_at?: string | null;
  closed_at?: string | null;
  product?: string | null;
  feature?: string | null;
  clients_affected?: number | null;
};

const PAGE_SIZE = 8;

type SortBy = "opened_at" | "severity";
type SortDir = "asc" | "desc";

export default function OpsPage() {
  /** Incidencias cargadas desde la API. */
  const [items, setItems] = useState<Incident[]>([]);
  /** KPIs para resumen ejecutivo. */
  const [kpis, setKpis] = useState<Kpis | null>(null);
  /** Error de carga de API. */
  const [error, setError] = useState<string | null>(null);

  // Filtros / estado UI
  const [q, setQ] = useState("");
  const [sevFilter, setSevFilter] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<SortBy>("opened_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Helpers: resetear pagina solo en acciones del usuario (sin setState en effects)
  const resetPage = () => setPage(1);

  /** Actualiza la query y reinicia paginacion. */
  const onQueryChange = (next: string) => {
    setQ(next);
    resetPage();
  };

  /** Activa/desactiva un filtro de severidad. */
  const toggleSev = (sev: string) => {
    setSevFilter((cur) => (cur === sev ? null : sev));
    resetPage();
  };

  /** Resetea todos los filtros. */
  const onResetFilters = () => {
    setSevFilter(null);
    setStatusFilter(null);
    setQ("");
    resetPage();
  };

  /** Cambia el criterio de ordenacion. */
  const onSortByChange = (next: SortBy) => {
    setSortBy(next);
    resetPage();
  };

  /** Alterna direccion de orden (asc/desc). */
  const toggleSortDir = () => {
    setSortDir((s) => (s === "asc" ? "desc" : "asc"));
    resetPage();
  };

  useEffect(() => {
    let alive = true;

    apiGet<Kpis>("/kpis")
      .then((r) => alive && setKpis(r))
      .catch((e) => alive && setError(String(e)));

    apiGet<{ items: Incident[] }>("/incidents")
      .then((r) => alive && setItems(r.items ?? []))
      .catch((e) => alive && setError(String(e)));

    return () => {
      alive = false;
    };
  }, []);

  // Derivado: filtrado + ordenado
  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    let arr = items.slice();

    if (sevFilter) {
      arr = arr.filter((it) => it.severity === sevFilter);
    }
    if (statusFilter) {
      arr = arr.filter((it) => it.status === statusFilter);
    }
    if (qq) {
      arr = arr.filter(
        (it) =>
          it.global_id.toLowerCase().includes(qq) ||
          (it.title ?? "").toLowerCase().includes(qq) ||
          (it.product ?? "").toLowerCase().includes(qq) ||
          (it.feature ?? "").toLowerCase().includes(qq)
      );
    }

    arr.sort((a, b) => {
      if (sortBy === "opened_at") {
        const da = a.opened_at ?? "";
        const db = b.opened_at ?? "";
        return sortDir === "asc" ? da.localeCompare(db) : db.localeCompare(da);
      }
      // Orden de severidad: CRITICAL > HIGH > MEDIUM > LOW > UNKNOWN
      const order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"] as const;
      const ia = order.indexOf(a.severity ?? "UNKNOWN");
      const ib = order.indexOf(b.severity ?? "UNKNOWN");
      return sortDir === "asc" ? ia - ib : ib - ia;
    });

    return arr;
  }, [items, q, sevFilter, statusFilter, sortBy, sortDir]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  // NOTE: do not set state inside an effect — compute a clamped "safePage" derived value
  const safePage = Math.min(Math.max(1, page), pageCount);
  const pageItems = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // Top stale (open > threshold) desde KPIs open_over_threshold_list
  const staleList = useMemo(() => {
    if (!kpis) return [];
    return kpis.open_over_threshold_list ?? [];
  }, [kpis]);

  // Resumen ejecutivo basado en KPIs
  const executiveSummary = useMemo(() => {
    if (!kpis) return null;
    const critical = kpis.open_by_severity?.CRITICAL ?? 0;
    const high = kpis.open_by_severity?.HIGH ?? 0;
    const open = kpis.open_total ?? 0;
    const stalePct = kpis.open_over_threshold_pct ?? 0;
    return {
      critical,
      high,
      open,
      stalePct,
    };
  }, [kpis]);

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
            Ops Executive
          </div>
          <h1 className="mt-4 text-3xl sm:text-4xl font-display font-semibold text-[color:var(--ink)]">
            Ops Executive
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[color:var(--text-60)]">
            Panel operativo: filtra, prioriza y actúa con contexto inmediato.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-[color:var(--text-55)]">
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              <Activity className="h-3.5 w-3.5 text-[color:var(--blue)]" />
              Open: {kpis?.open_total ?? "—"}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              Critical: {executiveSummary?.critical ?? 0}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-70)] px-3 py-1">
              Stale &gt; X días:{" "}
              {executiveSummary ? `${executiveSummary.stalePct.toFixed(1)}%` : "—"}
            </span>
          </div>
        </div>
      </section>

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
        {/* Izquierda: filtros + tabla */}
        <div className="space-y-4">
          {/* Filtros */}
          <div className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "120ms" }}>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                  FILTROS
                </div>
                <div className="text-xs text-[color:var(--text-50)]">Refina y prioriza incidencias</div>
              </div>
              <Filter className="h-4 w-4 text-[color:var(--blue)]" />
            </div>

            <div className="mt-4 flex flex-col xl:flex-row xl:items-center gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)]">
                  <Search className="h-4 w-4 text-[color:var(--blue)]" />
                  <input
                    className="w-full bg-transparent outline-none"
                    placeholder="Buscar por ID, título, producto..."
                    value={q}
                    onChange={(e) => onQueryChange(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <FilterChip
                  label="Critical"
                  active={sevFilter === "CRITICAL"}
                  onClick={() => toggleSev("CRITICAL")}
                  tone="critical"
                />
                <FilterChip
                  label="High"
                  active={sevFilter === "HIGH"}
                  onClick={() => toggleSev("HIGH")}
                  tone="high"
                />
                <FilterChip
                  label="Medium"
                  active={sevFilter === "MEDIUM"}
                  onClick={() => toggleSev("MEDIUM")}
                  tone="medium"
                />
                <FilterChip
                  label="Low"
                  active={sevFilter === "LOW"}
                  onClick={() => toggleSev("LOW")}
                  tone="low"
                />
                <button
                  className="ml-1 text-xs text-[color:var(--text-60)] hover:text-[color:var(--text-primary)]"
                  onClick={onResetFilters}
                >
                  Reset
                </button>
              </div>

              <div className="flex items-center gap-2">
                <select
                  className="text-sm rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-[color:var(--ink)] shadow-[inset_0_1px_0_var(--inset-highlight)] outline-none"
                  value={sortBy}
                  onChange={(e) => onSortByChange(e.target.value as SortBy)}
                >
                  <option value="opened_at">Orden por apertura</option>
                  <option value="severity">Orden por criticidad</option>
                </select>

                <button
                  className="rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--text-60)] shadow-[inset_0_1px_0_var(--inset-highlight)] hover:text-[color:var(--text-primary)]"
                  onClick={toggleSortDir}
                >
                  {sortDir === "asc" ? "asc" : "desc"}
                </button>
              </div>
            </div>
          </div>

          {/* Tabla */}
          <div className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] shadow-[var(--shadow-md)] backdrop-blur-xl overflow-hidden animate-rise" style={{ animationDelay: "180ms" }}>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-[color:var(--surface-80)] backdrop-blur border-b" style={{ borderColor: "var(--border)" }}>
                  <tr className="text-left text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-45)]">
                    <th className="px-3 py-3">ID</th>
                    <th className="px-3 py-3">Título</th>
                    <th className="px-3 py-3 text-center">Estado</th>
                    <th className="px-3 py-3 text-center">Criticidad</th>
                    <th className="px-3 py-3 text-center">Abierta</th>
                    <th className="px-3 py-3 text-center">Clientes</th>
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((it, idx) => (
                    <tr key={it.global_id} className={idx % 2 === 0 ? "bg-[color:var(--surface-70)]" : "bg-[color:var(--surface-40)]"} style={{ borderTop: "1px solid var(--border)" }}>
                      <td className="px-3 py-3 font-mono text-xs">{it.global_id}</td>
                      <td className="px-3 py-3">{it.title}</td>
                      <td className="px-3 py-3 text-center">
                        <StatusPill status={it.status} />
                      </td>
                      <td className="px-3 py-3 text-center">
                        <SeverityPill sev={it.severity} />
                      </td>
                      <td className="px-3 py-3 text-center">{it.opened_at ?? "-"}</td>
                      <td className="px-3 py-3 text-center">{it.clients_affected ?? "-"}</td>
                    </tr>
                  ))}

                  {pageItems.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-6 text-center text-[color:var(--text-50)]">
                        No hay incidencias para mostrar
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {/* Paginacion */}
              <div className="p-3 flex items-center justify-between text-sm">
                <div className="text-[color:var(--text-60)]">{filtered.length} resultados</div>
                <div className="flex items-center gap-2">
                  <button
                    className="rounded-full p-1 border border-[color:var(--border-60)] bg-[color:var(--surface-80)] shadow-sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={safePage === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <div className="px-2">
                    {safePage} / {pageCount}
                  </div>
                  <button
                    className="rounded-full p-1 border border-[color:var(--border-60)] bg-[color:var(--surface-80)] shadow-sm"
                    onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                    disabled={safePage === pageCount}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Columna derecha: paneles */}
        <div className="space-y-4">
          {/* Resumen ejecutivo */}
          <div className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "200ms" }}>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                  EXECUTIVE SUMMARY
                </div>
                <div className="text-xs text-[color:var(--text-60)]">Recomendaciones rápidas</div>
              </div>
              <Zap className="h-5 w-5 text-[color:var(--blue)]" />
            </div>

            <div className="mt-4 space-y-2 text-sm">
              <div>
                <b>{executiveSummary?.critical ?? 0}</b> CRITICAL abiertos — revisar
                primero.
              </div>
              <div>
                <b>{executiveSummary?.high ?? 0}</b> HIGH abiertos — asignar recursos.
              </div>
              <div className="text-xs text-[color:var(--text-60)]">
                {executiveSummary
                  ? `Total open: ${executiveSummary.open} · ${executiveSummary.stalePct.toFixed(
                      1
                    )}% > X días`
                  : "Cargando KPIs..."}
              </div>
            </div>
          </div>

          {/* Top stale */}
          <div className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "240ms" }}>
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                TOP STALE INCIDENTS
              </div>
              <Hourglass className="h-4 w-4 text-[color:var(--text-50)]" />
            </div>

            <div className="mt-3 space-y-2">
              {staleList.length === 0 && (
                <div className="text-sm text-[color:var(--text-60)]">No stale incidents detected</div>
              )}
              {staleList.slice(0, 6).map((gid) => (
                <div key={gid} className="flex items-center gap-2 justify-between">
                  <div className="text-sm font-mono text-[color:var(--ink)]">{gid}</div>
                  <div className="text-xs text-[color:var(--text-60)]">open</div>
                </div>
              ))}
            </div>
          </div>

          {/* Acciones rapidas */}
          <div className="rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel)] p-5 shadow-[var(--shadow-md)] backdrop-blur-xl animate-rise" style={{ animationDelay: "280ms" }}>
            <div className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--blue)]">
              QUICK ACTIONS
            </div>
            <div className="mt-4 flex flex-col gap-2">
              <ActionBtn
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Priorizar CRITICAL"
                onClick={() => alert("Priorizar CRITICAL (demo)")}
              />
              <ActionBtn
                icon={<Archive className="h-4 w-4" />}
                label="Exportar selección"
                onClick={() => alert("Export (demo)")}
              />
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-[var(--radius)] bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}
    </Shell>
  );
}

/* --------------------------- Piezas UI pequenas --------------------------- */

/** Boton de filtro con estado activo. */
function FilterChip({
  label,
  active,
  onClick,
  tone = "default",
}: {
  label: string;
  active?: boolean;
  onClick?: () => void;
  tone?: "critical" | "high" | "medium" | "low" | "default";
}) {
  const toneMap: Record<string, string> = {
    critical: "bg-rose-600 text-white",
    high: "bg-amber-500 text-white",
    medium: "bg-blue-500 text-white",
    low: "bg-emerald-500 text-white",
    default: "bg-[color:var(--overlay-10)] text-[color:var(--text-70)]",
  };
  const activeClass = toneMap[tone] ?? toneMap.default;
  return (
    <button
      onClick={onClick}
      className={
        "px-3 py-1 text-xs rounded-full border transition shadow-sm " +
        (active
          ? `${activeClass} border-transparent`
          : "bg-[color:var(--surface-80)] text-[color:var(--text-60)] border-[color:var(--border-60)]")
      }
      style={{ minWidth: 72 }}
    >
      {label}
    </button>
  );
}

/** Pildora visual para el estado de la incidencia. */
function StatusPill({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    OPEN: { label: "OPEN", cls: "bg-sky-50 text-sky-700 border-sky-200" },
    IN_PROGRESS: { label: "IN PROG", cls: "bg-purple-50 text-purple-700 border-purple-200" },
    CLOSED: { label: "CLOSED", cls: "bg-slate-50 text-slate-600 border-slate-200" },
    BLOCKED: { label: "BLOCKED", cls: "bg-rose-50 text-rose-700 border-rose-200" },
    UNKNOWN: { label: "UNKNOWN", cls: "bg-slate-50 text-slate-600 border-slate-200" },
  };
  const info = map[status] ?? map.UNKNOWN;
  return (
    <div className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${info.cls}`}>
      {info.label}
    </div>
  );
}

/** Pildora visual para la severidad de la incidencia. */
function SeverityPill({ sev }: { sev: string }) {
  const map: Record<string, { label: string; color: string }> = {
    CRITICAL: { label: "CRITICAL", color: "bg-rose-50 text-rose-700 border-rose-200" },
    HIGH: { label: "HIGH", color: "bg-amber-50 text-amber-700 border-amber-200" },
    MEDIUM: { label: "MEDIUM", color: "bg-blue-50 text-blue-700 border-blue-200" },
    LOW: { label: "LOW", color: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    UNKNOWN: { label: "UNKNOWN", color: "bg-slate-50 text-slate-600 border-slate-200" },
  };
  const info = map[sev] ?? map.UNKNOWN;
  return (
    <div className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${info.color}`}>
      {info.label}
    </div>
  );
}

/** Boton de accion rapida en el panel Ops. */
function ActionBtn({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)] shadow-sm hover:bg-[color:var(--surface-solid)]"
    >
      <div
        className="h-8 w-8 rounded-2xl grid place-items-center border border-[color:var(--border-70)] bg-[color:var(--surface-80)]"
      >
        {icon}
      </div>
      <div>{label}</div>
    </button>
  );
}
