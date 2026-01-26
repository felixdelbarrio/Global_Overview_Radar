"use client";

import { useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { Kpis, Severity } from "@/lib/types";

function sevOrder(): Severity[] {
  return ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];
}

function sevChip(sev: Severity) {
  if (sev === "CRITICAL") return { bg: "#FEE2E2", fg: "#991B1B" };
  if (sev === "HIGH") return { bg: "#FFEDD5", fg: "#9A3412" };
  if (sev === "MEDIUM") return { bg: "#FEF9C3", fg: "#854D0E" };
  if (sev === "LOW") return { bg: "#DCFCE7", fg: "#166534" };
  return { bg: "#E2E8F0", fg: "#334155" };
}

export default function OpsPage() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Kpis>("/kpis")
      .then(setKpis)
      .catch((e) => setError(String(e)));
  }, []);

  const openSev = useMemo(() => {
    const src = kpis?.open_by_severity;
    if (!src) return [];
    return sevOrder().map((s) => ({ s, v: src[s] ?? 0 }));
  }, [kpis]);

  return (
    <Shell>
      <h1 className="brr-title">Ops Executive</h1>
      <p className="brr-subtitle mt-1">
        Vista para daily: foco en criticidad, backlog y stale.
      </p>

      {error && (
        <div
          className="mt-4"
          style={{
            borderRadius: 18,
            background: "#FEF2F2",
            border: "1px solid #FECACA",
            padding: "12px 14px",
            color: "#991B1B",
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          {error}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="brr-card p-5">
          <div className="text-xs font-semibold text-[color:var(--bbva-muted)]">
            Backlog abierto
          </div>
          <div className="mt-1" style={{ fontSize: 44, fontWeight: 800 }}>
            {kpis?.open_total ?? "—"}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {openSev.map((x) => {
              const c = sevChip(x.s);
              return (
                <span
                  key={x.s}
                  className="brr-chip"
                  style={{ background: c.bg, color: c.fg }}
                >
                  {x.s} · {x.v}
                </span>
              );
            })}
          </div>
        </div>

        <div className="brr-card p-5">
          <div className="text-xs font-semibold text-[color:var(--bbva-muted)]">
            Open &gt; X días
          </div>
          <div className="mt-1" style={{ fontSize: 44, fontWeight: 800 }}>
            {(kpis?.open_over_threshold_pct ?? 0).toFixed(1)}%
          </div>

          <div className="mt-3 text-sm text-[color:var(--bbva-muted)]">
            IDs (si aplica)
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {(kpis?.open_over_threshold_list ?? []).length === 0 ? (
              <span className="text-sm text-[color:var(--bbva-muted)]">—</span>
            ) : (
              kpis?.open_over_threshold_list.map((id) => (
                <span key={id} className="brr-chip" style={{ background: "#E0F2FE", color: "#075985" }}>
                  {id}
                </span>
              ))
            )}
          </div>
        </div>

        <div className="brr-card p-5">
          <div className="text-xs font-semibold text-[color:var(--bbva-muted)]">
            Resolución media
          </div>
          <div className="mt-1" style={{ fontSize: 44, fontWeight: 800 }}>
            {kpis?.mean_resolution_days_overall ?? "—"}
          </div>
          <div className="text-sm text-[color:var(--bbva-muted)]">días (overall)</div>
        </div>
      </div>
    </Shell>
  );
}