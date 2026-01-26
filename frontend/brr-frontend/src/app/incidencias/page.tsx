"use client";

import { useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { Severity } from "@/lib/types";

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
  const s = (sev ?? "UNKNOWN").toUpperCase();
  if (s === "CRITICAL") return "bg-red-100 text-red-800";
  if (s === "HIGH") return "bg-orange-100 text-orange-800";
  if (s === "MEDIUM") return "bg-yellow-100 text-yellow-900";
  if (s === "LOW") return "bg-emerald-100 text-emerald-800";
  return "bg-slate-100 text-slate-700";
}

function chipStatus(st: string) {
  const s = (st ?? "").toUpperCase();
  if (s === "OPEN") return "bg-blue-100 text-blue-800";
  if (s === "IN_PROGRESS") return "bg-purple-100 text-purple-800";
  if (s === "CLOSED") return "bg-slate-100 text-slate-700";
  return "bg-slate-100 text-slate-700";
}

export default function IncidenciasPage() {
  const [items, setItems] = useState<Incident[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [sev, setSev] = useState<string>("ALL");
  const [st, setSt] = useState<string>("ALL");

  useEffect(() => {
    apiGet<{ items: Incident[] }>("/incidents")
      .then((r) => setItems(r.items))
      .catch((e) => setError(String(e)));
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

  return (
    <Shell>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="brr-title">Incidencias</h1>
          <p className="brr-subtitle mt-1">
            Listado consolidado desde los distintos orígenes.
          </p>
        </div>

        <div className="brr-pill">
          Total: <span className="font-semibold">{filtered.length}</span>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="mt-6 brr-card p-4">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_180px_180px] gap-3">
          <div>
            <div className="text-xs font-semibold text-[color:var(--bbva-muted)] mb-1">
              Buscar
            </div>
            <input
              className="brr-input"
              placeholder="ID, título, producto, funcionalidad…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>

          <div>
            <div className="text-xs font-semibold text-[color:var(--bbva-muted)] mb-1">
              Criticidad
            </div>
            <select className="brr-input" value={sev} onChange={(e) => setSev(e.target.value)}>
              <option value="ALL">Todas</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
              <option value="UNKNOWN">UNKNOWN</option>
            </select>
          </div>

          <div>
            <div className="text-xs font-semibold text-[color:var(--bbva-muted)] mb-1">
              Estado
            </div>
            <select className="brr-input" value={st} onChange={(e) => setSt(e.target.value)}>
              <option value="ALL">Todos</option>
              <option value="OPEN">OPEN</option>
              <option value="IN_PROGRESS">IN_PROGRESS</option>
              <option value="CLOSED">CLOSED</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="mt-6 brr-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-white/80 backdrop-blur border-b"
                  style={{ borderColor: "var(--bbva-border)" }}>
              <tr className="text-left">
                <th className="px-4 py-3 text-xs font-semibold text-[color:var(--bbva-muted)]">ID</th>
                <th className="px-4 py-3 text-xs font-semibold text-[color:var(--bbva-muted)]">Título</th>
                <th className="px-4 py-3 text-xs font-semibold text-[color:var(--bbva-muted)]">Estado</th>
                <th className="px-4 py-3 text-xs font-semibold text-[color:var(--bbva-muted)]">Criticidad</th>
                <th className="px-4 py-3 text-xs font-semibold text-[color:var(--bbva-muted)]">Producto</th>
                <th className="px-4 py-3 text-xs font-semibold text-[color:var(--bbva-muted)]">Funcionalidad</th>
                <th className="px-4 py-3 text-xs font-semibold text-[color:var(--bbva-muted)]">Abierta</th>
              </tr>
            </thead>

            <tbody>
              {filtered.map((it, idx) => (
                <tr
                  key={it.global_id}
                  className={idx % 2 === 0 ? "bg-white/60" : "bg-white/35"}
                  style={{ borderTop: "1px solid var(--bbva-border)" }}
                >
                  <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">
                    {it.global_id}
                  </td>
                  <td className="px-4 py-3 min-w-[360px]">
                    <div className="font-semibold text-[color:var(--bbva-text)]">
                      {it.title}
                    </div>
                    <div className="text-xs text-[color:var(--bbva-muted)]">
                      {it.product ?? "—"} · {it.feature ?? "—"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${chipStatus(it.status)}`}>
                      {it.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${chipSeverity(String(it.severity))}`}>
                      {String(it.severity)}
                    </span>
                  </td>
                  <td className="px-4 py-3">{it.product ?? "—"}</td>
                  <td className="px-4 py-3">{it.feature ?? "—"}</td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {it.opened_at ?? "—"}
                  </td>
                </tr>
              ))}

              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-[color:var(--bbva-muted)]">
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