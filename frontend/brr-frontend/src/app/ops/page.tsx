"use client";

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
  const [items, setItems] = useState<Incident[]>([]);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Filters / UI state
  const [q, setQ] = useState("");
  const [sevFilter, setSevFilter] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<SortBy>("opened_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Helpers: reset page ONLY in response to user actions (no setState in effects)
  const resetPage = () => setPage(1);

  const onQueryChange = (next: string) => {
    setQ(next);
    resetPage();
  };

  const toggleSev = (sev: string) => {
    setSevFilter((cur) => (cur === sev ? null : sev));
    resetPage();
  };

  const onResetFilters = () => {
    setSevFilter(null);
    setStatusFilter(null);
    setQ("");
    resetPage();
  };

  const onSortByChange = (next: SortBy) => {
    setSortBy(next);
    resetPage();
  };

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

  // Derived: filtered + sorted
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
      // severity ordering: CRITICAL > HIGH > MEDIUM > LOW > UNKNOWN
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

  // Top stale (open > threshold) from KPIs open_over_threshold_list (global_id strings)
  const staleList = useMemo(() => {
    if (!kpis) return [];
    return kpis.open_over_threshold_list ?? [];
  }, [kpis]);

  // Small executive summary based on KPIs
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
      <div
        className="rounded-[var(--radius)] border p-4"
        style={{
          background: "var(--panel)",
          borderColor: "var(--border)",
          boxShadow: "var(--shadow)",
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-[color:var(--bbva-navy)]">
              Ops Executive
            </h1>
            <p className="text-sm text-black/60 mt-1">
              Panel operativo: filtra, prioriza y actúa.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-xs text-black/55">Total incidencias</div>
            <div className="text-2xl font-semibold text-[color:var(--bbva-blue)]">
              {kpis?.open_total ?? "—"}
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
          {/* Left: Filters + table */}
          <div>
            {/* Filters */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <div
                className="flex items-center gap-2 rounded-[var(--radius)] border px-3 py-2"
                style={{
                  borderColor: "var(--border)",
                  background: "var(--panel-strong)",
                }}
              >
                <Search className="h-4 w-4 text-[color:var(--bbva-navy)]" />
                <input
                  className="bg-transparent outline-none text-sm min-w-0"
                  placeholder="Buscar por ID, título, producto..."
                  value={q}
                  onChange={(e) => onQueryChange(e.target.value)}
                />
              </div>

              <div className="flex items-center gap-2">
                <FilterChip
                  label="Critical"
                  active={sevFilter === "CRITICAL"}
                  onClick={() => toggleSev("CRITICAL")}
                  color="bg-red-600"
                />
                <FilterChip
                  label="High"
                  active={sevFilter === "HIGH"}
                  onClick={() => toggleSev("HIGH")}
                  color="bg-amber-500"
                />
                <FilterChip
                  label="Medium"
                  active={sevFilter === "MEDIUM"}
                  onClick={() => toggleSev("MEDIUM")}
                  color="bg-blue-500"
                />
                <FilterChip
                  label="Low"
                  active={sevFilter === "LOW"}
                  onClick={() => toggleSev("LOW")}
                  color="bg-emerald-500"
                />
                <button className="ml-2 text-sm text-black/60" onClick={onResetFilters}>
                  Reset
                </button>
              </div>

              <div className="ml-auto flex items-center gap-2">
                <select
                  className="text-sm rounded-md border px-2 py-1"
                  value={sortBy}
                  onChange={(e) => onSortByChange(e.target.value as SortBy)}
                >
                  <option value="opened_at">Orden por apertura</option>
                  <option value="severity">Orden por criticidad</option>
                </select>

                <button
                  className="rounded-md border px-2 py-1 text-sm"
                  onClick={toggleSortDir}
                >
                  {sortDir === "asc" ? "asc" : "desc"}
                </button>
              </div>
            </div>

            {/* Table */}
            <div
              className="mt-4 rounded-[var(--radius)] border overflow-x-auto"
              style={{
                borderColor: "var(--border)",
                background: "var(--panel-strong)",
              }}
            >
              <table className="min-w-full text-sm">
                <thead className="bg-black/5">
                  <tr>
                    <th className="px-3 py-2 text-left">ID</th>
                    <th className="px-3 py-2 text-left">Título</th>
                    <th className="px-3 py-2">Estado</th>
                    <th className="px-3 py-2">Criticidad</th>
                    <th className="px-3 py-2">Abierta</th>
                    <th className="px-3 py-2">Clientes</th>
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((it) => (
                    <tr key={it.global_id} className="border-t">
                      <td className="px-3 py-2 font-mono text-xs">{it.global_id}</td>
                      <td className="px-3 py-2">{it.title}</td>
                      <td className="px-3 py-2 text-center">
                        <StatusPill status={it.status} />
                      </td>
                      <td className="px-3 py-2 text-center">
                        <SeverityPill sev={it.severity} />
                      </td>
                      <td className="px-3 py-2 text-center">{it.opened_at ?? "-"}</td>
                      <td className="px-3 py-2 text-center">{it.clients_affected ?? "-"}</td>
                    </tr>
                  ))}

                  {pageItems.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-6 text-center text-black/50">
                        No hay incidencias para mostrar
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {/* Pagination */}
              <div className="p-3 flex items-center justify-between text-sm">
                <div className="text-black/60">{filtered.length} resultados</div>
                <div className="flex items-center gap-2">
                  <button
                    className="rounded-md p-1 border"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={safePage === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <div className="px-2">
                    {safePage} / {pageCount}
                  </div>
                  <button
                    className="rounded-md p-1 border"
                    onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                    disabled={safePage === pageCount}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Right column: panels */}
          <div className="space-y-4">
            {/* Executive summary */}
            <div
              className="rounded-[var(--radius)] border p-4"
              style={{ background: "var(--panel-strong)", borderColor: "var(--border)" }}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-[color:var(--bbva-navy)]">
                    Executive Summary
                  </div>
                  <div className="text-sm text-black/60">Recomendaciones rápidas</div>
                </div>
                <Zap className="h-5 w-5 text-[color:var(--bbva-blue)]" />
              </div>

              <div className="mt-3 space-y-2">
                <div className="text-sm">
                  <b>{executiveSummary?.critical ?? 0}</b> CRITICAL abiertos — revisar primero.
                </div>
                <div className="text-sm">
                  <b>{executiveSummary?.high ?? 0}</b> HIGH abiertos — asignar recursos.
                </div>
                <div className="text-sm text-black/60">
                  {executiveSummary
                    ? `Total open: ${executiveSummary.open} · ${executiveSummary.stalePct.toFixed(
                        1
                      )}% > X días`
                    : "Cargando KPIs..."}
                </div>
              </div>
            </div>

            {/* Top stale */}
            <div
              className="rounded-[var(--radius)] border p-4"
              style={{ background: "var(--panel-strong)", borderColor: "var(--border)" }}
            >
              <div className="flex items-center justify-between">
                <div className="text-xs font-semibold text-[color:var(--bbva-navy)]">
                  Top stale incidents
                </div>
                <Hourglass className="h-4 w-4 text-black/50" />
              </div>

              <div className="mt-3 space-y-2">
                {staleList.length === 0 && (
                  <div className="text-sm text-black/60">No stale incidents detected</div>
                )}
                {staleList.slice(0, 6).map((gid) => (
                  <div key={gid} className="flex items-center gap-2 justify-between">
                    <div className="text-sm font-mono text-[color:var(--bbva-navy)]">{gid}</div>
                    <div className="text-xs text-black/60">open</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick actions */}
            <div
              className="rounded-[var(--radius)] border p-4"
              style={{ background: "var(--panel-strong)", borderColor: "var(--border)" }}
            >
              <div className="text-xs font-semibold text-[color:var(--bbva-navy)]">
                Quick actions
              </div>
              <div className="mt-3 flex flex-col gap-2">
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
      </div>

      {error && (
        <div className="mt-4 rounded-[var(--radius)] bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}
    </Shell>
  );
}

/* ----------------------------- Small UI pieces ---------------------------- */

function FilterChip({
  label,
  active,
  onClick,
  color = "bg-black",
}: {
  label: string;
  active?: boolean;
  onClick?: () => void;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "px-3 py-1 text-sm rounded-full text-white/95 transition " +
        (active ? `${color} shadow` : "bg-black/10 text-black/70")
      }
      style={{ minWidth: 72 }}
    >
      {label}
    </button>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    OPEN: { label: "OPEN", cls: "text-white bg-amber-600 px-2 py-0.5 rounded-full text-xs" },
    IN_PROGRESS: { label: "IN PROG", cls: "text-white bg-blue-600 px-2 py-0.5 rounded-full text-xs" },
    CLOSED: { label: "CLOSED", cls: "text-white bg-black/30 px-2 py-0.5 rounded-full text-xs" },
    BLOCKED: { label: "BLOCKED", cls: "text-white bg-red-600 px-2 py-0.5 rounded-full text-xs" },
    UNKNOWN: { label: "UNKNOWN", cls: "text-black bg-black/10 px-2 py-0.5 rounded-full text-xs" },
  };
  const info = map[status] ?? map.UNKNOWN;
  return <div className={info.cls}>{info.label}</div>;
}

function SeverityPill({ sev }: { sev: string }) {
  const map: Record<string, { label: string; color: string }> = {
    CRITICAL: { label: "CRITICAL", color: "bg-red-600 text-white" },
    HIGH: { label: "HIGH", color: "bg-amber-500 text-white" },
    MEDIUM: { label: "MEDIUM", color: "bg-blue-500 text-white" },
    LOW: { label: "LOW", color: "bg-emerald-500 text-white" },
    UNKNOWN: { label: "UNKNOWN", color: "bg-black/10 text-black" },
  };
  const info = map[sev] ?? map.UNKNOWN;
  return (
    <div className={`px-2 py-0.5 rounded-full text-xs ${info.color}`}>
      {info.label}
    </div>
  );
}

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
      className="flex items-center gap-3 rounded-md border px-3 py-2 text-sm hover:bg-black/5"
    >
      <div
        className="h-8 w-8 rounded-2xl grid place-items-center border"
        style={{ borderColor: "var(--border)" }}
      >
        {icon}
      </div>
      <div>{label}</div>
    </button>
  );
}