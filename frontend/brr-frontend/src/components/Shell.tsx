"use client";

/**
 * Layout principal del frontend.
 *
 * Incluye topbar, sidebar y contenedor de contenido.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ListChecks,
  ShieldAlert,
  Database,
  Activity,
  HeartPulse,
  Layers,
  Loader2,
  Moon,
  Sun,
  Sparkles,
} from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import { dispatchIngestSuccess, INGEST_STARTED_EVENT } from "@/lib/events";
import { INCIDENTS_FEATURE_ENABLED } from "@/lib/flags";
import type { IngestJob, IngestJobKind, ReputationMeta } from "@/lib/types";

type ProfileOptionsResponse = {
  active: {
    source: string;
    profiles: string[];
    profile_key: string;
  };
  options: {
    default: string[];
    samples: string[];
  };
};

export function Shell({ children }: { children: React.ReactNode }) {
  const profileAppliedKey = "gor-profile-applied";
  const readStoredTheme = () => {
    try {
      if (typeof window === "undefined") return null;
      const storage = window.localStorage;
      if (!storage || typeof storage.getItem !== "function") return null;
      const stored = storage.getItem("gor-theme");
      return stored === "ambient-dark" || stored === "ambient-light" ? stored : null;
    } catch {
      return null;
    }
  };

  const persistTheme = (nextTheme: "ambient-light" | "ambient-dark") => {
    try {
      if (typeof window === "undefined") return;
      const storage = window.localStorage;
      if (!storage || typeof storage.setItem !== "function") return;
      storage.setItem("gor-theme", nextTheme);
    } catch {
      // ignore storage failures (private mode/tests)
    }
  };

  const [theme, setTheme] = useState<"ambient-light" | "ambient-dark">(() => {
    if (typeof window === "undefined") return "ambient-light";
    const stored = readStoredTheme();
    if (stored) return stored;
    const domTheme = document.documentElement.dataset.theme;
    if (domTheme === "ambient-dark" || domTheme === "ambient-light") {
      return domTheme;
    }
    return "ambient-light";
  });

  /** Ruta actual para resaltar la navegacion. */
  const pathname = usePathname();
  const [uiFlags, setUiFlags] = useState({
    incidents_enabled: true,
    ops_enabled: true,
  });
  const [incidentsAvailable, setIncidentsAvailable] = useState(false);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [ingestBusy, setIngestBusy] = useState<Record<IngestJobKind, boolean>>({
    reputation: false,
    incidents: false,
  });
  const [ingestJobs, setIngestJobs] = useState<Record<IngestJobKind, IngestJob | null>>({
    reputation: null,
    incidents: null,
  });
  const [profilesOpen, setProfilesOpen] = useState(false);
  const [profileOptions, setProfileOptions] = useState<ProfileOptionsResponse | null>(null);
  const [profileSource, setProfileSource] = useState<"default" | "samples">("default");
  const [profileSelection, setProfileSelection] = useState<string[]>([]);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileAppliedNote, setProfileAppliedNote] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let alive = true;
    apiGet<ReputationMeta>("/reputation/meta")
      .then((meta) => {
        if (!alive) return;
        const ui = meta.ui ?? {};
        setUiFlags({
          incidents_enabled: ui.incidents_enabled !== false,
          ops_enabled: ui.ops_enabled !== false,
        });
        setIncidentsAvailable(meta.incidents_available === true);
      })
      .catch(() => {
        if (!alive) return;
        setUiFlags({ incidents_enabled: true, ops_enabled: true });
        setIncidentsAvailable(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    apiGet<ProfileOptionsResponse>("/reputation/profiles")
      .then((data) => {
        if (!alive) return;
        setProfileOptions(data);
        const source = data.active.source === "samples" ? "samples" : "default";
        setProfileSource(source);
        setProfileSelection(data.active.profiles ?? []);
      })
      .catch(() => {
        if (!alive) return;
        setProfileOptions(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    try {
      if (typeof window === "undefined") return;
      const storage = window.localStorage;
      if (!storage) return;
      const flag = storage.getItem(profileAppliedKey);
      if (!flag) return;
      storage.removeItem(profileAppliedKey);
      setProfileAppliedNote(true);
      const timer = window.setTimeout(() => setProfileAppliedNote(false), 3200);
      return () => window.clearTimeout(timer);
    } catch {
      // ignore storage failures
    }
    return undefined;
  }, []);

  useEffect(() => {
    if (!profileOptions) return;
    const active = profileOptions.active;
    const source = active.source === "samples" ? "samples" : "default";
    if (source === profileSource) {
      setProfileSelection(active.profiles ?? []);
    } else {
      setProfileSelection([]);
    }
  }, [profileSource, profileOptions]);

  const ingestJobsRef = useRef(ingestJobs);

  useEffect(() => {
    ingestJobsRef.current = ingestJobs;
  }, [ingestJobs]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<IngestJob>).detail;
      if (!detail) return;
      setIngestJobs((prev) => ({ ...prev, [detail.kind]: detail }));
      setIngestOpen(true);
    };
    window.addEventListener(INGEST_STARTED_EVENT, handler as EventListener);
    return () => {
      window.removeEventListener(INGEST_STARTED_EVENT, handler as EventListener);
    };
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "ambient-light" ? "ambient-dark" : "ambient-light";
    setTheme(nextTheme);
    persistTheme(nextTheme);
  };

  const startIngest = async (kind: IngestJobKind) => {
    setIngestError(null);
    setIngestBusy((prev) => ({ ...prev, [kind]: true }));
    try {
      const payload = kind === "reputation" ? { force: false } : {};
      const job = await apiPost<IngestJob>(`/ingest/${kind}`, payload);
      setIngestJobs((prev) => ({ ...prev, [kind]: job }));
      setIngestOpen(true);
    } catch (err) {
      setIngestError(err instanceof Error ? err.message : "No se pudo iniciar la ingesta");
    } finally {
      setIngestBusy((prev) => ({ ...prev, [kind]: false }));
    }
  };

  const availableProfiles = profileOptions?.options[profileSource] ?? [];
  const toggleProfileSelection = (name: string) => {
    setProfileSelection((prev) =>
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
    );
  };
  const selectAllProfiles = () => {
    setProfileSelection(availableProfiles);
  };
  const clearProfiles = () => {
    setProfileSelection([]);
  };
  const applyProfiles = async () => {
    setProfileError(null);
    setProfileBusy(true);
    try {
      await apiPost("/reputation/profiles", {
        source: profileSource,
        profiles: profileSelection,
      });
      try {
        if (typeof window !== "undefined") {
          window.localStorage?.setItem(profileAppliedKey, "1");
        }
      } catch {
        // ignore storage failures
      }
      window.location.reload();
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "No se pudo aplicar el perfil");
    } finally {
      setProfileBusy(false);
    }
  };

  const ingestActive = useMemo(
    () =>
      Object.values(ingestJobs).some(
        (job) => job && (job.status === "queued" || job.status === "running")
      ),
    [ingestJobs]
  );

  useEffect(() => {
    if (!ingestActive) return;
    let alive = true;
    const poll = () => {
      const active = Object.values(ingestJobsRef.current).filter(
        (job) => job && (job.status === "queued" || job.status === "running")
      ) as IngestJob[];
      active.forEach((job) => {
        apiGet<IngestJob>(`/ingest/jobs/${job.id}`)
          .then((updated) => {
            if (!alive) return;
            const previous = ingestJobsRef.current[updated.kind];
            if (updated.status === "success" && previous?.status !== "success") {
              dispatchIngestSuccess({
                kind: updated.kind,
                finished_at: updated.finished_at ?? null,
              });
            }
            setIngestJobs((prev) => ({ ...prev, [updated.kind]: updated }));
          })
          .catch((err) => {
            if (!alive) return;
            setIngestError(err instanceof Error ? err.message : "Error al consultar ingesta");
          });
      });
    };

    poll();
    const interval = setInterval(poll, 1400);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, [ingestActive]);
  const ingestProgress = useMemo(() => {
    const active = Object.values(ingestJobs).filter(
      (job) => job && (job.status === "queued" || job.status === "running")
    ) as IngestJob[];
    if (!active.length) return 0;
    const total = active.reduce((acc, job) => acc + (job.progress ?? 0), 0);
    return Math.round(total / active.length);
  }, [ingestJobs]);

  const incidentsScopeEnabled = INCIDENTS_FEATURE_ENABLED && incidentsAvailable;
  const incidentsIngestEnabled =
    INCIDENTS_FEATURE_ENABLED &&
    incidentsAvailable &&
    uiFlags.incidents_enabled !== false;
  const showIngestCenter = true;
  const showIncidentsNav = incidentsScopeEnabled && uiFlags.incidents_enabled;
  const showOpsNav = incidentsScopeEnabled && uiFlags.ops_enabled;

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
      hidden: !showIncidentsNav,
    },
    {
      href: "/ops",
      label: "Ops Executive",
      icon: ShieldAlert,
      description: "Vista operativa",
      hidden: !showOpsNav,
    },
  ];

  return (
    <div className="min-h-screen">
      {/* Barra superior */}
      <header className="sticky top-0 z-40">
        <div
          className="h-16 px-6 flex items-center gap-4 text-white shadow-[var(--shadow-header)]"
          style={{
            background: "var(--nav-gradient)",
          }}
        >
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-[color:var(--surface-12)] border border-[color:var(--border-18)] grid place-items-center">
              <Activity className="h-5 w-5 text-white" />
            </div>
            <div className="leading-tight">
              <div className="font-display font-semibold tracking-tight">
                Global Overview Radar
              </div>
              <div className="text-[11px] text-[color:var(--text-inverse-75)] -mt-0.5">
                Enterprise Incident Intelligence
              </div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3 text-xs text-[color:var(--text-inverse-80)]">
            {showIngestCenter && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setIngestOpen((prev) => !prev)}
                  aria-label="Centro de ingestas"
                  title="Centro de ingestas"
                  className="relative h-9 w-9 rounded-full border border-[color:var(--border-15)] overflow-hidden"
                >
                  <span
                    className="absolute inset-0"
                    style={{
                      background: ingestActive
                        ? `conic-gradient(from 210deg, var(--aqua) 0 ${ingestProgress}%, rgba(255,255,255,0.18) ${ingestProgress}% 100%)`
                        : "radial-gradient(circle at 20% 20%, rgba(255,255,255,0.35), rgba(255,255,255,0.05) 65%)",
                    }}
                  />
                  <span className="absolute inset-[2px] rounded-full bg-[color:var(--surface-10)] backdrop-blur" />
                  <span className="relative z-10 h-full w-full grid place-items-center text-white">
                    <Sparkles className={ingestActive ? "h-4 w-4 animate-pulse" : "h-4 w-4"} />
                  </span>
                </button>

                {ingestOpen && (
                  <div className="absolute right-0 mt-3 w-[320px] rounded-[22px] border border-[color:var(--border-60)] bg-[color:var(--panel-strong)] shadow-[var(--shadow-lg)] backdrop-blur-xl overflow-hidden z-50">
                    <div className="absolute -top-12 -right-12 h-32 w-32 rounded-full bg-[color:var(--aqua)]/20 blur-3xl" />
                    <div className="absolute -bottom-16 left-6 h-36 w-36 rounded-full bg-[color:var(--blue)]/10 blur-3xl" />
                    <div className="relative p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-xs font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                            CENTRO DE INGESTA
                          </div>
                          <div className="mt-1 text-sm text-[color:var(--text-60)]">
                            Lanza procesos en segundo plano sin frenar tu flujo.
                          </div>
                        </div>
                        {ingestActive && (
                          <div className="flex items-center gap-2 text-[11px] text-[color:var(--text-55)]">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            {ingestProgress}% listo
                          </div>
                        )}
                      </div>

                      {(["reputation", "incidents"] as IngestJobKind[])
                        .filter((kind) => kind === "reputation" || incidentsIngestEnabled)
                        .map((kind) => {
                        const job = ingestJobs[kind];
                        const busy =
                          ingestBusy[kind] ||
                          job?.status === "queued" ||
                          job?.status === "running";
                        const isError = job?.status === "error";
                        const isSuccess = job?.status === "success";
                        const label =
                          kind === "reputation"
                            ? "Ingesta reputación"
                            : "Ingesta incidencias";
                        const detail =
                          kind === "reputation"
                            ? "Señales externas + sentimiento"
                            : "Fuentes internas + consolidación";
                        const metaBits: string[] = [];
                        const items = job?.meta?.items;
                        if (typeof items === "number") {
                          metaBits.push(`${items} items`);
                        }
                        const observations = job?.meta?.observations;
                        if (typeof observations === "number") {
                          metaBits.push(`${observations} observaciones`);
                        }
                        const incidents = job?.meta?.incidents;
                        if (typeof incidents === "number") {
                          metaBits.push(`${incidents} incidencias`);
                        }
                        const sources = job?.meta?.sources;
                        if (typeof sources === "number") {
                          metaBits.push(`${sources} fuentes`);
                        }
                        const warning =
                          typeof job?.meta?.warning === "string" ? job.meta.warning : "";
                        const metaLabel = metaBits.join(" · ");
                        return (
                          <button
                            key={kind}
                            type="button"
                            onClick={() => startIngest(kind)}
                            disabled={busy}
                            className="group relative w-full overflow-hidden rounded-[18px] border border-[color:var(--border-60)] bg-[color:var(--surface-80)] p-3 text-left transition hover:shadow-[var(--shadow-soft)] disabled:opacity-70"
                          >
                            <div className="absolute inset-0 opacity-0 transition group-hover:opacity-100" style={{ background: "radial-gradient(140px 60px at 0% 0%, rgba(45,204,205,0.18), transparent 60%)" }} />
                            <div className="relative flex items-start gap-3">
                              <div className="h-10 w-10 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] grid place-items-center">
                                {kind === "reputation" ? (
                                  <Sparkles className="h-5 w-5 text-[color:var(--blue)]" />
                                ) : (
                                  <ListChecks className="h-5 w-5 text-[color:var(--blue)]" />
                                )}
                              </div>
                              <div className="flex-1">
                                <div className="text-sm font-semibold text-[color:var(--ink)]">
                                  {label}
                                </div>
                                <div className="text-xs text-[color:var(--text-60)]">{detail}</div>
                                {job?.stage && (
                                  <div className="mt-2 text-[11px] text-[color:var(--text-50)]">
                                    {job.stage}
                                  </div>
                                )}
                                {metaLabel && (
                                  <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-40)]">
                                    {metaLabel}
                                  </div>
                                )}
                                {warning && (
                                  <div className="mt-1 text-[10px] text-[color:var(--text-50)]">
                                    {warning}
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center gap-2 text-xs">
                                {busy && <Loader2 className="h-4 w-4 animate-spin text-[color:var(--blue)]" />}
                                {isSuccess && !busy && (
                                  <span className="rounded-full bg-[color:var(--surface-60)] px-2 py-0.5 text-[10px] text-[color:var(--text-60)]">
                                    OK
                                  </span>
                                )}
                                {isError && !busy && (
                                  <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] text-rose-700">
                                    Error
                                  </span>
                                )}
                              </div>
                            </div>

                            {job && (
                              <div className="relative mt-3 h-2 w-full rounded-full bg-[color:var(--surface-10)] overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-[color:var(--aqua)] via-[color:var(--blue)] to-transparent transition-all"
                                  style={{ width: `${job.progress ?? 0}%` }}
                                />
                              </div>
                            )}
                          </button>
                        );
                      })}

                      {ingestError && (
                        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                          {ingestError}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="relative">
              <button
                type="button"
                onClick={() => setProfilesOpen((prev) => !prev)}
                aria-label="Cambiar perfil"
                title="Cambiar perfil"
                className="h-9 px-3 rounded-full flex items-center gap-2 border border-[color:var(--border-15)] bg-[color:var(--surface-10)] text-[color:var(--text-inverse-80)] transition hover:bg-[color:var(--surface-15)] hover:text-white"
              >
                <Layers className="h-4 w-4" />
                <span className="text-xs">Perfil</span>
              </button>
              {profileAppliedNote && (
                <span className="absolute right-0 -bottom-6 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-10)] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-inverse-80)]">
                  Perfil aplicado
                </span>
              )}
              {profilesOpen && (
                <div className="absolute right-0 mt-3 w-[280px] rounded-[20px] border border-[color:var(--border-60)] bg-[color:var(--panel-strong)] shadow-[var(--shadow-lg)] backdrop-blur-xl overflow-hidden z-50">
                  <div className="relative p-4 space-y-3">
                    <div className="text-xs font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                      PERFIL
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setProfileSource("default")}
                        className={`flex-1 rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.2em] ${
                          profileSource === "default"
                            ? "border-[color:var(--aqua)] text-white bg-[color:var(--surface-70)]"
                            : "border-[color:var(--border-60)] text-[color:var(--text-55)]"
                        }`}
                      >
                        Producción
                      </button>
                      <button
                        type="button"
                        onClick={() => setProfileSource("samples")}
                        className={`flex-1 rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.2em] ${
                          profileSource === "samples"
                            ? "border-[color:var(--aqua)] text-white bg-[color:var(--surface-70)]"
                            : "border-[color:var(--border-60)] text-[color:var(--text-55)]"
                        }`}
                      >
                        Plantillas
                      </button>
                    </div>

                    <div className="max-h-48 space-y-2 overflow-auto pr-1">
                      {availableProfiles.length ? (
                        availableProfiles.map((profile) => (
                          <label
                            key={profile}
                            className="flex items-center gap-3 rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2 text-sm text-[color:var(--ink)]"
                          >
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-[color:var(--aqua)]"
                              checked={profileSelection.includes(profile)}
                              onChange={() => toggleProfileSelection(profile)}
                            />
                            <span className="truncate">{profile}</span>
                          </label>
                        ))
                      ) : (
                        <div className="text-xs text-[color:var(--text-55)]">
                          No hay perfiles disponibles.
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={selectAllProfiles}
                          className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-55)]"
                        >
                          Todos
                        </button>
                        <button
                          type="button"
                          onClick={clearProfiles}
                          className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-55)]"
                        >
                          Limpiar
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={applyProfiles}
                        disabled={profileBusy}
                        className="rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-4 py-1 text-xs text-white disabled:opacity-70"
                      >
                        {profileBusy ? "Aplicando..." : "Aplicar"}
                      </button>
                    </div>
                    {profileError && (
                      <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                        {profileError}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={
                theme === "ambient-light"
                  ? "Cambiar a modo oscuro"
                  : "Cambiar a modo claro"
              }
              title={
                theme === "ambient-light"
                  ? "Ambient dark"
                  : "Ambient light"
              }
              className="h-9 w-9 rounded-full grid place-items-center border border-[color:var(--border-15)] bg-[color:var(--surface-10)] text-[color:var(--text-inverse-80)] transition hover:bg-[color:var(--surface-15)] hover:text-white active:scale-95"
            >
              {theme === "ambient-light" ? (
                <Moon className="h-4 w-4" />
              ) : (
                <Sun className="h-4 w-4" />
              )}
            </button>
            <span className="hidden sm:inline-flex items-center gap-2 rounded-full bg-[color:var(--surface-10)] border border-[color:var(--border-15)] px-3 py-1">
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
                        : "text-[color:var(--brand-ink)] hover:bg-[color:var(--overlay-5)]")
                    }
                    style={
                      active
                        ? {
                            borderRadius: 18,
                            background: "var(--nav-active-gradient)",
                            boxShadow: "var(--nav-active-shadow)",
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
                          ? "border-[color:var(--border-20)] bg-[color:var(--surface-10)]"
                          : "border-[color:var(--border)] bg-[color:var(--surface-60)]")
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
                            ? "text-[11px] text-[color:var(--text-inverse-70)]"
                            : "text-[11px] text-[color:var(--text-50)]"
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
                          : "bg-transparent group-hover:bg-[color:var(--overlay-20)]")
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
