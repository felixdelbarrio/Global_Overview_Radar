"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";

type Incident = {
  global_id: string;
  title: string;
  status: string;
  severity: string;
  opened_at?: string | null;
  closed_at?: string | null;
  product?: string | null;
  feature?: string | null;
};

type IncidentsApiShape =
  | Incident[]
  | { items: Incident[] }
  | { incidents: Incident[] }
  | Record<string, unknown>;

function normalizeIncidents(payload: IncidentsApiShape): Incident[] {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === "object") {
    const p = payload as any;
    if (Array.isArray(p.items)) return p.items as Incident[];
    if (Array.isArray(p.incidents)) return p.incidents as Incident[];
  }
  return [];
}

async function apiGetRaw<T = unknown>(path: string): Promise<T> {
  // Si ya tienes apiGet en "@/lib/api", puedes reemplazar esta función
  // por tu apiGet. Esto es “a prueba de balas” y da errores más claros.
  const base =
    process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

  const url = `${base}${path.startsWith("/") ? "" : "/"}${path}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    // credentials: "include", // solo si usas cookies
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${text || "sin body"}`);
  }

  return (await res.json()) as T;
}

export default function IncidenciasPage() {
  const [items, setItems] = useState<Incident[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        setLoading(true);
        setError(null);

        const raw = await apiGetRaw<IncidentsApiShape>("/incidents");
        const normalized = normalizeIncidents(raw);

        if (!alive) return;

        setItems(normalized);

        // Si no llega nada, dejamos pista para debug sin romper la UI
        if (normalized.length === 0) {
          // eslint-disable-next-line no-console
          console.warn("Incidents payload shape not recognized:", raw);
        }
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!alive) return;
        setLoading(false);
      }
    })();

    return () => {
      alive = false;
    };
  }, []);

  return (
    <Shell>
      <h1 className="text-2xl font-semibold text-[color:var(--bbva-navy)]">Incidencias</h1>
      <p className="text-sm text-black/60 mt-1">
        Listado de incidencias consolidadas desde los distintos orígenes.
      </p>

      {error && (
        <div className="mt-4 rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-800">
          <div className="font-semibold">Error cargando incidencias</div>
          <div className="mt-1 break-words">{error}</div>
          <div className="mt-2 text-xs text-red-700/80">
            Tip: prueba abrir <span className="font-mono">http://127.0.0.1:8000/incidents</span> en el
            navegador y mira si devuelve <span className="font-mono">items</span> o un array.
          </div>
        </div>
      )}

      <div className="mt-6 rounded-2xl bg-white border border-black/5 shadow-sm overflow-x-auto">
        <div className="px-3 py-3 border-b bg-black/[0.02] text-sm text-black/70 flex items-center gap-3">
          <span className="font-medium">Total:</span> {loading ? "Cargando..." : items.length}
          <span className="ml-auto text-xs text-black/50">
            API: {process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"}
          </span>
        </div>

        <table className="min-w-full text-sm">
          <thead className="bg-black/5">
            <tr>
              <th className="px-3 py-2 text-left">ID</th>
              <th className="px-3 py-2 text-left">Título</th>
              <th className="px-3 py-2 text-center">Estado</th>
              <th className="px-3 py-2 text-center">Criticidad</th>
              <th className="px-3 py-2 text-left">Producto</th>
              <th className="px-3 py-2 text-left">Funcionalidad</th>
              <th className="px-3 py-2 text-center">Abierta</th>
            </tr>
          </thead>

          <tbody>
            {!loading &&
              items.map((it) => (
                <tr key={it.global_id} className="border-t hover:bg-black/[0.02]">
                  <td className="px-3 py-2 font-mono text-xs">{it.global_id}</td>
                  <td className="px-3 py-2">{it.title}</td>
                  <td className="px-3 py-2 text-center">{it.status}</td>
                  <td className="px-3 py-2 text-center">{it.severity}</td>
                  <td className="px-3 py-2">{it.product ?? "-"}</td>
                  <td className="px-3 py-2">{it.feature ?? "-"}</td>
                  <td className="px-3 py-2 text-center">{it.opened_at ?? "-"}</td>
                </tr>
              ))}

            {!loading && items.length === 0 && !error && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-black/50">
                  No hay incidencias para mostrar
                </td>
              </tr>
            )}

            {loading && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-black/50">
                  Cargando incidencias...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}