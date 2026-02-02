"use client";

/**
 * Layout principal del frontend.
 *
 * Incluye topbar, sidebar y contenedor de contenido.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ListChecks,
  ShieldAlert,
  Database,
  Activity,
  HeartPulse,
} from "lucide-react";
import { apiGet } from "@/lib/api";
import type { ReputationMeta } from "@/lib/types";

export function Shell({ children }: { children: React.ReactNode }) {
  /** Ruta actual para resaltar la navegacion. */
  const pathname = usePathname();
  const [uiFlags, setUiFlags] = useState({
    incidents_enabled: true,
    ops_enabled: true,
  });

  useEffect(() => {
    if (process.env.NODE_ENV === "test") return;
    let alive = true;
    apiGet<ReputationMeta>("/reputation/meta")
      .then((meta) => {
        if (!alive) return;
        const ui = meta.ui ?? {};
        setUiFlags({
          incidents_enabled: ui.incidents_enabled !== false,
          ops_enabled: ui.ops_enabled !== false,
        });
      })
      .catch(() => {
        if (!alive) return;
        setUiFlags({ incidents_enabled: true, ops_enabled: true });
      });
    return () => {
      alive = false;
    };
  }, []);

  /** Definicion de items de navegacion. */
  const nav = [
    {
      href: "/",
      label: "Dashboard",
      icon: LayoutDashboard,
      description: "Señales clave",
    },
    {
      href: "/sentimiento",
      label: "Sentimiento",
      icon: HeartPulse,
      description: "Histórico y análisis",
    },
    {
      href: "/incidencias",
      label: "Incidencias",
      icon: ListChecks,
      description: "Listado y filtros",
      hidden: !uiFlags.incidents_enabled,
    },
    {
      href: "/ops",
      label: "Ops Executive",
      icon: ShieldAlert,
      description: "Vista operativa",
      hidden: !uiFlags.ops_enabled,
    },
  ];

  return (
    <div className="min-h-screen">
      {/* Barra superior */}
      <header className="sticky top-0 z-40">
        <div
          className="h-16 px-6 flex items-center gap-4 text-white shadow-[0_10px_30px_rgba(7,33,70,0.18)]"
          style={{
            background:
              "linear-gradient(90deg, var(--navy), var(--blue) 55%, rgba(45,204,205,0.55))",
          }}
        >
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-white/12 border border-white/18 grid place-items-center">
              <Activity className="h-5 w-5 text-white" />
            </div>
            <div className="leading-tight">
              <div className="font-display font-semibold tracking-tight">
                Global Overview Radar
              </div>
              <div className="text-[11px] text-white/75 -mt-0.5">
                Enterprise Incident Intelligence
              </div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3 text-xs text-white/80">
            <span className="hidden sm:inline-flex items-center gap-2 rounded-full bg-white/10 border border-white/15 px-3 py-1">
              <Database className="h-4 w-4" />
              API proxied en <span className="text-white">/api</span>
            </span>
          </div>
        </div>
      </header>

      {/* Layout principal */}
      <div className="mx-auto max-w-7xl px-4 py-6 grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-6">
        {/* Barra lateral */}
        <aside
          className="h-fit rounded-[var(--radius)] border backdrop-blur-xl"
          style={{
            background: "var(--panel)",
            borderColor: "var(--border)",
            boxShadow: "var(--shadow)",
          }}
        >
          <div className="p-4">
            <div className="text-xs font-semibold tracking-wide text-[color:var(--blue)]">
              NAVEGACIÓN
            </div>

            <nav className="mt-3 flex flex-col gap-2">
              {nav.filter((item) => !item.hidden).map((item) => {
                const active = pathname === item.href;
                const Icon = item.icon;

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={
                      "group flex items-center gap-3 px-3 py-2 transition " +
                      (active
                        ? "text-white"
                        : "text-[color:var(--navy)] hover:bg-black/5")
                    }
                    style={
                      active
                        ? {
                            borderRadius: 18,
                            background:
                              "linear-gradient(90deg, rgba(0,68,129,0.95), rgba(7,33,70,0.92))",
                            boxShadow:
                              "0 12px 22px rgba(0, 68, 129, 0.22)",
                          }
                        : {
                            borderRadius: 18,
                          }
                    }
                  >
                    <div
                      className={
                        "h-9 w-9 grid place-items-center border transition " +
                        (active
                          ? "border-white/20 bg-white/10"
                          : "border-[color:var(--border)] bg-white/60")
                      }
                      style={{ borderRadius: 16 }}
                    >
                      <Icon
                        className={
                          active
                            ? "h-5 w-5 text-white"
                            : "h-5 w-5 text-[color:var(--blue)]"
                        }
                      />
                    </div>

                    <div className="flex-1">
                      <div
                        className={
                          active
                            ? "text-sm font-semibold"
                            : "text-sm font-medium"
                        }
                      >
                        {item.label}
                      </div>
                      <div
                        className={
                          active
                            ? "text-[11px] text-white/70"
                            : "text-[11px] text-black/50"
                        }
                      >
                        {item.description}
                      </div>
                    </div>

                    <div
                      className={
                        "h-2 w-2 rounded-full transition " +
                        (active
                          ? "bg-[color:var(--aqua)]"
                          : "bg-transparent group-hover:bg-black/20")
                      }
                    />
                  </Link>
                );
              })}
            </nav>
          </div>
        </aside>

        {/* Contenido */}
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
