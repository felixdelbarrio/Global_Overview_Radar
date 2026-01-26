"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const API_LABEL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function cx(...s: Array<string | false | null | undefined>) {
  return s.filter(Boolean).join(" ");
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const navItem = (href: string, label: string) => {
    const active = pathname === href;

    return (
      <Link
        href={href}
        className={cx(
          "flex items-center gap-2 px-3 py-2 text-sm font-semibold transition",
          active ? "text-white" : "text-[color:var(--bbva-text)]"
        )}
        style={
          active
            ? {
                borderRadius: 14,
                background:
                  "linear-gradient(135deg, rgba(0,68,129,1) 0%, rgba(7,33,70,1) 100%)",
                border: "1px solid rgba(255,255,255,0.12)",
                boxShadow: "0 10px 24px rgba(7,33,70,0.20)",
              }
            : {
                borderRadius: 14,
                border: "1px solid transparent",
              }
        }
      >
        {label}
      </Link>
    );
  };

  return (
    <div className="min-h-screen">
      {/* Topbar */}
      <header className="sticky top-0 z-50">
        <div
          className="h-16 px-6 flex items-center gap-4"
          style={{
            background:
              "linear-gradient(135deg, rgba(7,33,70,1) 0%, rgba(0,68,129,1) 55%, rgba(7,33,70,1) 100%)",
            borderBottom: "1px solid rgba(255,255,255,0.10)",
          }}
        >
          <div className="flex items-center gap-3">
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: 16,
                background: "rgba(255,255,255,0.10)",
                border: "1px solid rgba(255,255,255,0.14)",
                boxShadow: "0 10px 22px rgba(0,0,0,0.25)",
                display: "grid",
                placeItems: "center",
                color: "white",
                fontWeight: 800,
                letterSpacing: 0.5,
              }}
            >
              BRR
            </div>
            <div className="leading-tight">
              <div className="text-white font-semibold">
                BBVA BugResolutionRadar
              </div>
              <div className="text-white/70 text-xs">
                Enterprise Incident Intelligence
              </div>
            </div>
          </div>

          <div className="ml-auto">
            <span
              className="brr-pill"
              style={{
                background: "rgba(255,255,255,0.10)",
                borderColor: "rgba(255,255,255,0.14)",
              }}
            >
              API · {API_LABEL}
            </span>
          </div>
        </div>
      </header>

      {/* Layout */}
      <div className="mx-auto max-w-7xl px-4 py-6 grid grid-cols-1 md:grid-cols-[260px_1fr] gap-6">
        {/* Sidebar */}
        <aside className="brr-card p-3 h-fit">
          <div className="px-2 pb-2 text-xs font-semibold tracking-wide text-[color:var(--bbva-muted)]">
            NAVEGACIÓN
          </div>

          <nav className="flex flex-col gap-1">
            {navItem("/", "Dashboard")}
            {navItem("/incidencias", "Incidencias")}
            {navItem("/ops", "Ops Executive")}
          </nav>

          <div
            className="mt-4"
            style={{
              borderRadius: 18,
              border: "1px solid var(--bbva-border)",
              background: "rgba(255,255,255,0.65)",
              padding: 12,
            }}
          >
            <div className="text-xs font-semibold text-[color:var(--bbva-text)]">
              Tip rápido
            </div>
            <div className="mt-1 text-xs text-[color:var(--bbva-muted)]">
              Prioriza incidencias <span className="font-semibold">CRITICAL/HIGH</span>{" "}
              en el daily.
            </div>
          </div>
        </aside>

        {/* Main */}
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}