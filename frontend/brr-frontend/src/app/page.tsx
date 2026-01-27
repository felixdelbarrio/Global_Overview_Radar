"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { EvolutionPoint, Kpis } from "@/lib/types";

const EvolutionChart = dynamic(
  () =>
    import("@/components/EvolutionChart").then((m) => m.EvolutionChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full rounded-xl bg-black/5 animate-pulse" />
    ),
  },
);

export default function DashboardPage() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [evolution, setEvolution] = useState<EvolutionPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
      <h1 className="text-2xl font-semibold text-[color:var(--bbva-navy)]">
        Dashboard Ejecutivo
      </h1>
      <p className="text-sm text-black/60 mt-1">
        Estado actual, criticidad y evolución de incidencias.
      </p>

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
      <div className="mt-8 rounded-2xl bg-white border border-black/5 p-5 shadow-sm">
        <h2 className="text-sm font-medium text-[color:var(--bbva-navy)]">
          Evolución temporal
        </h2>

        <div className="mt-4 h-72 min-h-[288px]">
          <EvolutionChart data={evolution} />
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
      className={
        "rounded-2xl bg-white border shadow-sm px-4 py-3 " +
        (highlight ? "border-[color:var(--bbva-blue)]" : "border-black/5")
      }
    >
      <div className="text-xs text-black/50">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-[color:var(--bbva-navy)]">
        {value}
      </div>
    </div>
  );
}
