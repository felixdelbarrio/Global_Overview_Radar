"use client";

import { useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { EvolutionPoint, Kpis, Severity } from "@/lib/types";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function sevLabel(s: Severity) {
  return s === "CRITICAL"
    ? "Critical"
    : s === "HIGH"
    ? "High"
    : s === "MEDIUM"
    ? "Medium"
    : s === "LOW"
    ? "Low"
    : "Unknown";
}

function sevChipClass(s: Severity) {
  switch (s) {
    case "CRITICAL":
      return "brr-chip bg-red-100 text-red-800";
    case "HIGH":
      return "brr-chip bg-orange-100 text-orange-800";
    case "MEDIUM":
      return "brr-chip bg-yellow-100 text-yellow-900";
    case "LOW":
      return "brr-chip bg-emerald-100 text-emerald-800";
    default:
      return "brr-chip bg-slate-100 text-slate-700";
  }
}

export default function DashboardPage() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [evolution, setEvolution] = useState<EvolutionPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    apiGet<Kpis>("/kpis")
      .then((r) => alive && setKpis(r))
      .catch((e) => alive && setError(String(e)));

    apiGet<{ days: number; series: EvolutionPoint[] }>("/evolution?days=60")
      .then((r) => alive && setEvolution(r.series))
      .catch((e) => alive && setError(String(e)));

    return () => {
      alive = false;
    };
  }, []);

  const openBySeverity = useMemo(() => {
    const src = kpis?.open_by_severity;
    if (!src) return [];
    const order: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];
    return order.map((s) => ({ severity: s, value: src[s] ?? 0 }));
  }, [kpis]);

  return (
    <Shell>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="brr-title">Dashboard Ejecutivo</h1>
          <p className="brr-subtitle mt-1">
            Estado actual, criticidad y evolución de incidencias.
          </p>
        </div>

        <div className="hidden md:flex items-center gap-2">
          <span className="brr-pill">Últimos 60 días</span>
          <span className="brr-pill">Fuente: cache.json</span>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* KPI cards */}
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi label="Incidencias abiertas" value={kpis?.open_total ?? "—"} highlight />
        <Kpi label="Nuevas (periodo)" value={kpis?.new_total ?? "—"} />
        <Kpi label="Cerradas (periodo)" value={kpis?.closed_total ?? "—"} />
        <Kpi
          label="Open > X días"
          value={`${(kpis?.open_over_threshold_pct ?? 0).toFixed(1)}%`}
        />
      </div>

      {/* Severity strip */}
      <div className="mt-4 brr-card px-4 py-3">
        <div className="text-xs font-semibold text-[color:var(--bbva-muted)]">
          Abiertas por criticidad
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {openBySeverity.map((x) => (
            <span key={x.severity} className={sevChipClass(x.severity)}>
              {sevLabel(x.severity)} · {x.value}
            </span>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="mt-6 brr-card p-5">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-[color:var(--bbva-text)]">
              Evolución temporal
            </h2>
            <p className="text-xs text-[color:var(--bbva-muted)]">
              Abiertas vs nuevas vs cerradas (últimos 60 días)
            </p>
          </div>
        </div>

        <div className="mt-4 w-full">
          <div className="h-[320px] min-h-[320px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={evolution}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(d: string) => d.slice(5)}
                  fontSize={11}
                />
                <YAxis fontSize={11} />
                <Tooltip />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="open"
                  name="Abiertas"
                  fill="#004481"
                  stroke="#004481"
                  fillOpacity={0.16}
                />
                <Area
                  type="monotone"
                  dataKey="new"
                  name="Nuevas"
                  fill="#2dcccd"
                  stroke="#2dcccd"
                  fillOpacity={0.20}
                />
                <Area
                  type="monotone"
                  dataKey="closed"
                  name="Cerradas"
                  fill="#99a4b3"
                  stroke="#99a4b3"
                  fillOpacity={0.14}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Kpi({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: number | string;
  highlight?: boolean;
}) {
  return (
    <div
      className="rounded-2xl bg-white/85 backdrop-blur border px-4 py-3 shadow-sm"
      style={{
        borderColor: highlight ? "rgba(0,68,129,0.45)" : "var(--bbva-border)",
        boxShadow: "0 10px 26px rgba(7,33,70,0.08)",
      }}
    >
      <div className="text-xs font-semibold text-[color:var(--bbva-muted)]">
        {label}
      </div>
      <div className="mt-1 text-3xl font-semibold tracking-tight text-[color:var(--bbva-text)]">
        {value}
      </div>
    </div>
  );
}