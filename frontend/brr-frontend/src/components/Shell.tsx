"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ListChecks,
  ShieldAlert,
  Database,
  Activity,
} from "lucide-react";

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const nav = [
    { href: "/", label: "Dashboard", icon: LayoutDashboard },
    { href: "/incidencias", label: "Incidencias", icon: ListChecks },
    { href: "/ops", label: "Ops Executive", icon: ShieldAlert },
  ];

  return (
    <div className="min-h-screen">
      {/* Top bar */}
      <header className="sticky top-0 z-40">
        <div
          className="h-16 px-6 flex items-center gap-4 text-white shadow-[0_10px_30px_rgba(7,33,70,0.18)]"
          style={{
            background:
              "linear-gradient(90deg, var(--bbva-navy), var(--bbva-blue) 55%, rgba(45,204,205,0.55))",
          }}
        >
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-white/12 border border-white/18 grid place-items-center">
              <Activity className="h-5 w-5 text-white" />
            </div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight">
                BBVA BugResolutionRadar
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

      {/* Main layout */}
      <div className="mx-auto max-w-7xl px-4 py-6 grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-6">
        {/* Sidebar */}
        <aside
          className="h-fit rounded-[var(--radius)] border backdrop-blur-xl"
          style={{
            background: "var(--panel)",
            borderColor: "var(--border)",
            boxShadow: "var(--shadow)",
          }}
        >
          <div className="p-4">
            <div className="text-xs font-semibold tracking-wide text-[color:var(--bbva-blue)]">
              NAVEGACIÓN
            </div>

            <nav className="mt-3 flex flex-col gap-2">
              {nav.map((item) => {
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
                        : "text-[color:var(--bbva-navy)] hover:bg-black/5")
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
                            : "h-5 w-5 text-[color:var(--bbva-blue)]"
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
                        {item.href === "/"
                          ? "KPIs y tendencias"
                          : item.href === "/incidencias"
                          ? "Listado y filtros"
                          : "Vista operativa"}
                      </div>
                    </div>

                    <div
                      className={
                        "h-2 w-2 rounded-full transition " +
                        (active
                          ? "bg-[color:var(--bbva-aqua)]"
                          : "bg-transparent group-hover:bg-black/20")
                      }
                    />
                  </Link>
                );
              })}
            </nav>
          </div>
        </aside>

        {/* Content */}
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}