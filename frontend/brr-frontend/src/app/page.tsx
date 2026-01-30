"use client";

/**
 * Dashboard ejecutivo: KPIs y evolucion temporal.
 */

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { EvolutionPoint, Kpis } from "@/lib/types";
import { Activity, Calendar, Sparkles } from "lucide-react";

const EvolutionChart = dynamic(
  () =>
    import("@/components/EvolutionChart").then((m) => m.EvolutionChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full rounded-[22px] border border-white/60 bg-white/70 animate-pulse" />
    ),
  },
);

export default function DashboardPage() {
  /** KPIs actuales. */
  const [kpis, setKpis] = useState<Kpis | null>(null);
  /** Serie temporal de evolucion. */
  const [evolution, setEvolution] = useState<EvolutionPoint[]>([]);
  /** Error de carga (si aplica). */
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    /** Control simple para evitar setState tras un unmount. */
    let alive = true;

    apiGet<Kpis>("/kpis")
      .then((r) => {
        if (alive) setKpis(r);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });

    apiGet<{ days: number; series: EvolutionPoint[] }>("/evolution?days=60")
      .then((r) => {
        if (alive) setEvolution(r.series);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });

    return () => {
      alive = false;
    };
  }, []);

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
            Executive overview
          </div>
          <h1 className="mt-4 text-3xl sm:text-4xl font-display font-semibold text-[color:var(--bbva-ink)]">
            Dashboard Ejecutivo
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-black/60">
            Estado actual, criticidad y evolución de incidencias para priorizar
            acciones.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-black/55">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              <Calendar className="h-3.5 w-3.5 text-[color:var(--bbva-blue)]" />
              Últimos 60 días
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              <Activity className="h-3.5 w-3.5 text-[color:var(--bbva-blue)]" />
              Open: {kpis?.open_total ?? "—"}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1">
              Nuevas: {kpis?.new_total ?? "—"}
            </span>
          </div>
        </div>
      </section>

      {error && (
        <div className="mt-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* KPIs */}
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi
          label="Incidencias abiertas"
          value={kpis?.open_total ?? "—"}
          highlight
        />
        <Kpi label="Nuevas (periodo)" value={kpis?.new_total ?? "—"} />
        <Kpi label="Cerradas (periodo)" value={kpis?.closed_total ?? "—"} />
        <Kpi
          label="Open > X días"
          value={`${(kpis?.open_over_threshold_pct ?? 0).toFixed(1)}%`}
        />
      </div>

      {/* Evolución */}
      <div className="mt-8 rounded-[26px] border border-white/60 bg-[color:var(--panel)] p-5 shadow-[0_20px_50px_rgba(7,33,70,0.08)] backdrop-blur-xl animate-rise" style={{ animationDelay: "180ms" }}>
        <h2 className="text-[11px] font-semibold tracking-[0.3em] text-[color:var(--bbva-blue)]">
          EVOLUCIÓN TEMPORAL
        </h2>

        <div className="mt-4 h-72 min-h-[288px]">
          <EvolutionChart data={evolution} />
        </div>
      </div>
    </Shell>
  );
}

/** Tarjeta KPI individual. */
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
      className={
        "relative overflow-hidden rounded-2xl border border-white/70 bg-white/85 px-4 py-3 shadow-[0_16px_40px_rgba(7,33,70,0.12)] animate-rise " +
        (highlight ? "ring-2 ring-[color:var(--bbva-aqua)]/30" : "")
      }
    >
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
