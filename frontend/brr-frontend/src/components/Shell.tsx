"use client";

/**
 * Layout principal del frontend.
 *
 * Incluye topbar, sidebar y contenedor de contenido.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Activity,
  HeartPulse,
  Layers,
  Loader2,
  Moon,
  Search,
  Sun,
  Sparkles,
  X,
  SlidersHorizontal,
} from "lucide-react";
import { apiGet, apiGetCached, apiPost } from "@/lib/api";
import {
  dispatchIngestStarted,
  dispatchIngestSuccess,
  dispatchProfileChanged,
  dispatchSettingsChanged,
  INGEST_STARTED_EVENT,
} from "@/lib/events";
import type { IngestJob, IngestJobKind } from "@/lib/types";

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

type ReputationSettingsField = {
  key: string;
  label: string;
  description?: string | null;
  type: "boolean" | "string" | "secret" | "number" | "select";
  value: string | number | boolean;
  options?: string[] | null;
  placeholder?: string | null;
};

type ReputationSettingsGroup = {
  id: string;
  label: string;
  description?: string | null;
  fields: ReputationSettingsField[];
};

type ReputationSettingsResponse = {
  groups: ReputationSettingsGroup[];
  updated_at?: string | null;
  advanced_options?: string[];
};

const EMPTY_PROFILES: string[] = [];
const LANGUAGE_LABELS: Record<string, string> = {
  es: "Español",
  en: "Inglés",
  fr: "Francés",
  de: "Alemán",
  it: "Italiano",
  pt: "Portugués",
  ar: "Árabe",
  ru: "Ruso",
  zh: "Chino",
  nl: "Neerlandés",
  no: "Noruego",
  sv: "Sueco",
  he: "Hebreo",
  ud: "Urdu",
};
const ADVANCED_LOG_KEYS = new Set([
  "advanced.log_enabled",
  "advanced.log_to_file",
  "advanced.log_file_name",
  "advanced.log_debug",
]);
const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

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

  const [theme, setTheme] = useState<"ambient-light" | "ambient-dark">("ambient-dark");
  const [themeReady, setThemeReady] = useState(false);

  /** Ruta actual para resaltar la navegacion. */
  const pathname = usePathname();
  const [ingestOpen, setIngestOpen] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [ingestBusy, setIngestBusy] = useState<Record<IngestJobKind, boolean>>({
    reputation: false,
  });
  const [ingestJobs, setIngestJobs] = useState<Record<IngestJobKind, IngestJob | null>>({
    reputation: null,
  });
  const [profilesOpen, setProfilesOpen] = useState(false);
  const [profileOptions, setProfileOptions] = useState<ProfileOptionsResponse | null>(null);
  const [profileSelection, setProfileSelection] = useState<string[]>([]);
  const [profileQuery, setProfileQuery] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileCategoryWarning, setProfileCategoryWarning] = useState<string | null>(null);
  const [sectorFocus, setSectorFocus] = useState<string>("all");
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [profileAppliedNote, setProfileAppliedNote] = useState(false);
  const [autoIngestNote, setAutoIngestNote] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsGroups, setSettingsGroups] = useState<ReputationSettingsGroup[] | null>(
    null,
  );
  const [settingsDraft, setSettingsDraft] = useState<Record<string, string | number | boolean>>(
    {},
  );
  const [settingsBase, setSettingsBase] = useState<Record<string, string | number | boolean>>(
    {},
  );
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [advancedKey, setAdvancedKey] = useState("");
  const [advancedValue, setAdvancedValue] = useState("");
  const [advancedError, setAdvancedError] = useState<string | null>(null);
  const [advancedOptions, setAdvancedOptions] = useState<string[]>([]);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  type FloatingPanel = "ingest" | "profiles" | "settings";

  const closeAllPanels = () => {
    setIngestOpen(false);
    setProfilesOpen(false);
    setSettingsOpen(false);
    setTemplatesOpen(false);
  };

  const openPanel = useCallback((panel: FloatingPanel) => {
    setIngestOpen(panel === "ingest");
    setProfilesOpen(panel === "profiles");
    setSettingsOpen(panel === "settings");
    if (panel !== "profiles") {
      setTemplatesOpen(false);
    }
  }, []);

  const toggleIngestPanel = () => {
    if (ingestOpen) {
      setIngestOpen(false);
      return;
    }
    openPanel("ingest");
  };

  const toggleSettingsPanel = () => {
    if (settingsOpen) {
      setSettingsOpen(false);
      return;
    }
    openPanel("settings");
  };

  const settingsFieldMap = useMemo(() => {
    const map = new Map<string, ReputationSettingsField>();
    settingsGroups?.forEach((group) => {
      group.fields.forEach((field) => {
        map.set(field.key, field);
      });
    });
    return map;
  }, [settingsGroups]);

  useEffect(() => {
    const stored = readStoredTheme();
    const domTheme = document.documentElement.dataset.theme;
    const next =
      stored ??
      (domTheme === "ambient-dark" || domTheme === "ambient-light"
        ? domTheme
        : "ambient-dark");
    setTheme(next);
    setThemeReady(true);
  }, [openPanel]);

  useEffect(() => {
    if (!themeReady) return;
    document.documentElement.dataset.theme = theme;
  }, [theme, themeReady]);

  useEffect(() => {
    let alive = true;
    apiGetCached<ProfileOptionsResponse>("/reputation/profiles", { ttlMs: 60000 })
      .then((data) => {
        if (!alive) return;
        setProfileOptions(data);
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
      const autoFlag = storage.getItem("gor-auto-ingest");
      if (!flag && !autoFlag) return;
      if (flag) {
        storage.removeItem(profileAppliedKey);
        setProfileAppliedNote(true);
      }
      if (autoFlag) {
        storage.removeItem("gor-auto-ingest");
        setAutoIngestNote(true);
      }
      const timer = window.setTimeout(() => {
        setProfileAppliedNote(false);
        setAutoIngestNote(false);
      }, 3200);
      return () => window.clearTimeout(timer);
    } catch {
      // ignore storage failures
    }
    return undefined;
  }, []);

  useEffect(() => {
    if (!profilesOpen) {
      setTemplatesOpen(false);
      setProfileCategoryWarning(null);
      return;
    }
    if (!templatesOpen) return;
    setProfileQuery("");
    setProfileCategoryWarning(null);
    setSectorFocus("all");
  }, [profilesOpen, templatesOpen]);

  useEffect(() => {
    if (!settingsOpen) return;
    let alive = true;
    setSettingsError(null);
    apiGet<ReputationSettingsResponse>("/reputation/settings")
      .then((data) => {
        if (!alive) return;
        setSettingsGroups(data.groups);
        const nextBase: Record<string, string | number | boolean> = {};
        data.groups.forEach((group) => {
          group.fields.forEach((field) => {
            nextBase[field.key] = field.value;
          });
        });
        setSettingsBase(nextBase);
        setSettingsDraft(nextBase);
        setAdvancedOptions(data.advanced_options ?? []);
        setAdvancedOpen(false);
        setAdvancedKey("");
        setAdvancedValue("");
        setAdvancedError(null);
      })
      .catch((err) => {
        if (!alive) return;
        setSettingsGroups(null);
        setSettingsError(err instanceof Error ? err.message : "No se pudo cargar la configuración");
        setAdvancedError(null);
        setAdvancedOptions([]);
      });
    return () => {
      alive = false;
    };
  }, [settingsOpen]);

  const ingestJobsRef = useRef(ingestJobs);

  useEffect(() => {
    ingestJobsRef.current = ingestJobs;
  }, [ingestJobs]);
  const ingestWasActiveRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<IngestJob>).detail;
      if (!detail) return;
      setIngestJobs((prev) => ({ ...prev, [detail.kind]: detail }));
      openPanel("ingest");
    };
    window.addEventListener(INGEST_STARTED_EVENT, handler as EventListener);
    return () => {
      window.removeEventListener(INGEST_STARTED_EVENT, handler as EventListener);
    };
  }, [openPanel]);

  const toggleTheme = () => {
    const nextTheme = theme === "ambient-light" ? "ambient-dark" : "ambient-light";
    setTheme(nextTheme);
    persistTheme(nextTheme);
  };

  const startIngest = async (kind: IngestJobKind) => {
    setIngestError(null);
    setIngestBusy((prev) => ({ ...prev, [kind]: true }));
    try {
      const job = await apiPost<IngestJob>(`/ingest/${kind}`, {
        force: false,
        all_sources: false,
      });
      setIngestJobs((prev) => ({ ...prev, [kind]: job }));
      openPanel("ingest");
    } catch (err) {
      setIngestError(err instanceof Error ? err.message : "No se pudo iniciar la ingesta");
    } finally {
      setIngestBusy((prev) => ({ ...prev, [kind]: false }));
    }
  };

  const activeProfiles = profileOptions?.active.profiles ?? EMPTY_PROFILES;
  const availableProfiles = useMemo(
    () => profileOptions?.options.samples ?? EMPTY_PROFILES,
    [profileOptions],
  );
  const normalizedProfileQuery = useMemo(
    () => profileQuery.trim().toLowerCase(),
    [profileQuery],
  );
  const filteredProfiles = useMemo(() => {
    if (!normalizedProfileQuery) return availableProfiles;
    return availableProfiles.filter((profile) =>
      profile.toLowerCase().includes(normalizedProfileQuery),
    );
  }, [availableProfiles, normalizedProfileQuery]);
  const selectedCount = profileSelection.length;
  const activeCount = activeProfiles.length;
  const applyDisabled = profileBusy || (templatesOpen && selectedCount === 0);
  const emptySelectionHint = templatesOpen && selectedCount === 0;
  const selectionBadge = templatesOpen
    ? selectedCount
      ? `${selectedCount} seleccionados`
      : "Plantillas"
    : activeCount
      ? `${activeCount} activo${activeCount > 1 ? "s" : ""}`
      : "Sin perfil";
  const settingsDirty = useMemo(() => {
    const keys = new Set([...Object.keys(settingsBase), ...Object.keys(settingsDraft)]);
    for (const key of keys) {
      if (settingsBase[key] !== settingsDraft[key]) return true;
    }
    return false;
  }, [settingsBase, settingsDraft]);

  const credentialSourceRows = useMemo(
    () => [
      {
        id: "newsapi",
        toggleKey: "sources.newsapi",
        keyKeys: ["keys.newsapi"],
      },
      {
        id: "guardian",
        toggleKey: "sources.guardian",
        keyKeys: ["keys.guardian"],
      },
      {
        id: "reddit",
        toggleKey: "sources.reddit",
        keyKeys: ["keys.reddit_id", "keys.reddit_secret"],
      },
      {
        id: "twitter",
        toggleKey: "sources.twitter",
        keyKeys: ["keys.twitter_bearer"],
      },
      {
        id: "google_reviews",
        toggleKey: "sources.google_reviews",
        keyKeys: ["keys.google_places"],
      },
      {
        id: "youtube",
        toggleKey: "sources.youtube",
        keyKeys: ["keys.youtube"],
      },
    ],
    []
  );

  const credentialIssues = useMemo(() => {
    const issues: { id: string; label: string; missing: string[] }[] = [];
    const isBlank = (value: unknown) => !String(value ?? "").trim();
    credentialSourceRows.forEach((row) => {
      const toggleValue = Boolean(settingsDraft[row.toggleKey]);
      if (!toggleValue) return;
      const missing = row.keyKeys.filter((key) => isBlank(settingsDraft[key]));
      if (missing.length) {
        const labelField = settingsFieldMap.get(row.toggleKey);
        const label = labelField?.label ?? row.id;
        issues.push({ id: row.id, label, missing });
      }
    });
    return issues;
  }, [credentialSourceRows, settingsDraft, settingsFieldMap]);

  const hasCredentialIssues = credentialIssues.length > 0;
  const advancedLogEnabled = Boolean(settingsDraft["advanced.log_enabled"]);
  const advancedLocked = !advancedLogEnabled;
  const availableAdvancedOptions = useMemo(() => {
    const used = new Set(
      Object.keys(settingsDraft)
        .filter((key) => key.startsWith("advanced."))
        .map((key) => key.replace(/^advanced\./, ""))
    );
    return advancedOptions.filter((option) => !used.has(option));
  }, [advancedOptions, settingsDraft]);

  const categoryKey = (value: string) => value.split("_")[0]?.toLowerCase() || "custom";
  const categoryMetaByKey = (key: string) => {
    const map: Record<string, { label: string; tone: string }> = {
      banking: { label: "Finanzas", tone: "var(--aqua)" },
      crypto: { label: "Cripto", tone: "var(--blue)" },
      sports: { label: "Deporte", tone: "var(--blue)" },
      streaming: { label: "Streaming", tone: "var(--aqua)" },
      travel: { label: "Travel", tone: "var(--blue)" },
      fashion: { label: "Moda", tone: "var(--aqua)" },
      automotive: { label: "Auto", tone: "var(--blue)" },
      taylor: { label: "Music", tone: "var(--aqua)" },
    };
    return map[key] ?? { label: key.toUpperCase(), tone: "var(--text-45)" };
  };
  const selectedCategoryKey = useMemo(
    () => (profileSelection.length ? categoryKey(profileSelection[0]) : null),
    [profileSelection],
  );
  const activeSectorKey =
    selectedCategoryKey ?? (sectorFocus !== "all" ? sectorFocus : null);

  const formatProfileLabel = (value: string) =>
    value
      .split("_")
      .filter(Boolean)
      .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
      .join(" ");

  const categoryMeta = (value: string) => categoryMetaByKey(categoryKey(value));

  const sectorOptions = useMemo(() => {
    const keys = new Set<string>();
    availableProfiles.forEach((profile) => keys.add(categoryKey(profile)));
    const order = [
      "banking",
      "crypto",
      "sports",
      "streaming",
      "travel",
      "fashion",
      "automotive",
      "taylor",
    ];
    const sorted = Array.from(keys).sort((a, b) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      const ra = ia === -1 ? 999 : ia;
      const rb = ib === -1 ? 999 : ib;
      if (ra !== rb) return ra - rb;
      return a.localeCompare(b);
    });
    return sorted.map((key) => ({ key, ...categoryMetaByKey(key) }));
  }, [availableProfiles]);

  const profilesToRender = useMemo(() => {
    if (!templatesOpen || !activeSectorKey) return filteredProfiles;
    return filteredProfiles.filter((profile) => categoryKey(profile) === activeSectorKey);
  }, [filteredProfiles, activeSectorKey, templatesOpen]);

  const primaryActiveProfile = activeProfiles[0] ?? "";
  const primaryActiveLabel = primaryActiveProfile
    ? formatProfileLabel(primaryActiveProfile)
    : "Sin perfil activo";
  const primaryActiveMeta = primaryActiveProfile
    ? categoryMeta(primaryActiveProfile)
    : null;
  const extraActiveCount = activeProfiles.length > 1 ? activeProfiles.length - 1 : 0;

  const resetProfileTemplateState = () => {
    setProfileSelection([]);
    setProfileQuery("");
    setSectorFocus("all");
    setProfileCategoryWarning(null);
  };

  const toggleProfileTemplates = () => {
    if (profilesOpen && templatesOpen) {
      setProfilesOpen(false);
      return;
    }
    openPanel("profiles");
    setTemplatesOpen(true);
    resetProfileTemplateState();
  };


  const toggleProfileSelection = (name: string) => {
    setProfileSelection((prev) => {
      if (prev.includes(name)) {
        const next = prev.filter((item) => item !== name);
        if (next.length <= 1) {
          setProfileCategoryWarning(null);
        }
        return next;
      }
      const nextKey = categoryKey(name);
      const currentKey = prev.length ? categoryKey(prev[0]) : activeSectorKey;
      if (currentKey && currentKey !== nextKey) {
        const label = categoryMetaByKey(currentKey).label;
        setProfileCategoryWarning(
          `Solo puedes combinar perfiles del sector ${label}.`,
        );
        return prev;
      }
      setProfileCategoryWarning(null);
      return [...prev, name];
    });
  };
  const applyProfiles = async () => {
    setProfileError(null);
    setProfileBusy(true);
    try {
      const response = await apiPost<{
        active?: { source: string; profiles: string[]; profile_key: string };
        auto_ingest?: { started?: boolean; job?: IngestJob };
      }>("/reputation/profiles", {
        source: "samples",
        profiles: profileSelection,
      });
      const autoStarted = response?.auto_ingest?.started === true;
      if (autoStarted && response?.auto_ingest?.job) {
        dispatchIngestStarted(response.auto_ingest.job);
      }
      if (response?.active) {
        dispatchProfileChanged(response.active);
      } else {
        dispatchProfileChanged({ source: "samples", profiles: profileSelection });
      }
      setProfileAppliedNote(true);
      setAutoIngestNote(autoStarted);
      if (typeof window !== "undefined") {
        window.setTimeout(() => {
          setProfileAppliedNote(false);
          setAutoIngestNote(false);
        }, 3200);
      }

      setProfilesOpen(false);

      const profiles = await apiGetCached<ProfileOptionsResponse>("/reputation/profiles", {
        ttlMs: 60000,
        force: true,
      }).catch(() => null);
      if (profiles) {
        setProfileOptions(profiles);
        setProfileSelection(profiles.active.profiles ?? []);
      }
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "No se pudo aplicar el perfil");
    } finally {
      setProfileBusy(false);
    }
  };

  const updateSettingValue = (key: string, value: string | number | boolean) => {
    setSettingsDraft((prev) => ({ ...prev, [key]: value }));
  };

  const resetSettingsDraft = () => {
    setSettingsDraft(settingsBase);
    setSettingsError(null);
  };

  const resetSettingsToDefault = async () => {
    if (typeof window !== "undefined") {
      const confirmed = window.confirm(
        "¿Restablecer la configuración de Menciones a los valores por defecto?"
      );
      if (!confirmed) return;
    }
    setSettingsOpen(false);
    setSettingsBusy(true);
    setSettingsError(null);
    try {
      const response = await apiPost<ReputationSettingsResponse>(
        "/reputation/settings/reset",
        {}
      );
      setSettingsGroups(response.groups);
      const nextBase: Record<string, string | number | boolean> = {};
      response.groups.forEach((group) => {
        group.fields.forEach((field) => {
          nextBase[field.key] = field.value;
        });
      });
      setSettingsBase(nextBase);
      setSettingsDraft(nextBase);
      setAdvancedOptions(response.advanced_options ?? []);
      dispatchSettingsChanged({ updated_at: response.updated_at ?? null });
      setSettingsSaved(true);
      if (typeof window !== "undefined") {
        window.setTimeout(() => setSettingsSaved(false), 2600);
      }
    } catch (err) {
      setSettingsError(
        err instanceof Error ? err.message : "No se pudo restablecer la configuración"
      );
      openPanel("settings");
    } finally {
      setSettingsBusy(false);
    }
  };

  const addAdvancedSetting = () => {
    setAdvancedError(null);
    const rawKey = advancedKey.trim();
    if (!rawKey) {
      setAdvancedError("Selecciona una variable.");
      return;
    }
    const settingsKey = `advanced.${rawKey}`;
    if (settingsDraft[settingsKey] !== undefined) {
      setAdvancedError("Esa variable ya existe.");
      return;
    }
    setSettingsDraft((prev) => ({ ...prev, [settingsKey]: advancedValue }));
    setSettingsGroups((prev) => {
      if (!prev) return prev;
      return prev.map((group) => {
        if (group.id !== "advanced") return group;
        return {
          ...group,
          fields: [
            ...group.fields,
            {
              key: settingsKey,
              label: rawKey,
              description: "Variable avanzada",
              type: "string",
              value: advancedValue,
            },
          ],
        };
      });
    });
    setAdvancedKey("");
    setAdvancedValue("");
  };

  const saveSettings = async () => {
    if (!settingsDirty || hasCredentialIssues) return;
    setSettingsOpen(false);
    setSettingsBusy(true);
    setSettingsError(null);
    try {
      const updates: Record<string, string | number | boolean> = {};
      Object.keys(settingsDraft).forEach((key) => {
        if (settingsDraft[key] !== settingsBase[key]) {
          updates[key] = settingsDraft[key];
        }
      });
      const response = await apiPost<ReputationSettingsResponse>("/reputation/settings", {
        values: updates,
      });
      setSettingsGroups(response.groups);
      const nextBase: Record<string, string | number | boolean> = {};
      response.groups.forEach((group) => {
        group.fields.forEach((field) => {
          nextBase[field.key] = field.value;
        });
      });
      setSettingsBase(nextBase);
      setSettingsDraft(nextBase);
      setAdvancedOptions(response.advanced_options ?? []);
      dispatchSettingsChanged({ updated_at: response.updated_at ?? null });
      setSettingsSaved(true);
      if (typeof window !== "undefined") {
        window.setTimeout(() => setSettingsSaved(false), 2600);
      }
    } catch (err) {
      setSettingsError(err instanceof Error ? err.message : "No se pudo guardar la configuración");
      openPanel("settings");
    } finally {
      setSettingsBusy(false);
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
    const wasActive = ingestWasActiveRef.current;
    ingestWasActiveRef.current = ingestActive;
    if (!wasActive || ingestActive || !ingestOpen) return undefined;
    if (profilesOpen || settingsOpen) return undefined;
    const hasSuccess = Object.values(ingestJobs).some(
      (job) => job && job.status === "success"
    );
    if (!hasSuccess) return undefined;
    const timeout = window.setTimeout(() => {
      setIngestOpen(false);
    }, 1200);
    return () => window.clearTimeout(timeout);
  }, [ingestActive, ingestJobs, ingestOpen, profilesOpen, settingsOpen]);

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

  const showIngestCenter = !AUTH_ENABLED;

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
  ];
  const anyPanelOpen = ingestOpen || profilesOpen || settingsOpen;

  return (
    <div className="min-h-screen">
      {/* Barra superior */}
      <header className="sticky top-0 z-40">
        <div
          className="relative mobile-header-showcase min-h-16 px-4 sm:px-6 py-4 sm:py-0 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4 text-white shadow-[var(--shadow-header)]"
          style={{
            background: "var(--nav-gradient)",
          }}
        >
          {/* Logo */}
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <div className="h-8 w-8 sm:h-9 sm:w-9 rounded-full bg-[color:var(--surface-12)] border border-[color:var(--border-18)] grid place-items-center">
              <Activity className="h-4 w-4 sm:h-5 sm:w-5 text-white" />
            </div>
            <div className="leading-tight min-w-0">
              <div className="font-display font-semibold tracking-tight text-[13px] sm:text-base leading-tight truncate">
                Global Overview Radar
              </div>
              <div className="text-[11px] text-[color:var(--text-inverse-75)] -mt-0.5 hidden sm:block">
                Enterprise Reputation Intelligence
              </div>
            </div>
          </div>

          <div className="ml-0 sm:ml-auto w-full sm:w-auto flex flex-wrap items-center justify-end sm:justify-start gap-2 sm:gap-3 text-xs text-[color:var(--text-inverse-80)]">
            {anyPanelOpen && (
              <button
                type="button"
                aria-label="Cerrar panel"
                onClick={closeAllPanels}
                className="fixed inset-0 z-[65] bg-transparent sm:hidden"
              />
            )}
            <div className="flex items-center gap-2 order-1 w-auto sm:order-none">
              {showIngestCenter && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={toggleIngestPanel}
                    aria-label="Centro de ingestas"
                    title="Centro de ingestas"
                    className="relative h-8 w-8 sm:h-9 sm:w-9 rounded-full border border-[color:var(--border-15)] overflow-hidden"
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
                    <div className="fixed left-1/2 top-[calc(env(safe-area-inset-top)+6.5rem)] bottom-[calc(env(safe-area-inset-bottom)+5.5rem)] z-[70] mt-0 w-[92vw] max-w-[360px] -translate-x-1/2 rounded-[22px] border border-[color:var(--border-60)] bg-[color:var(--panel-strong)] shadow-[var(--shadow-lg)] backdrop-blur-xl overflow-y-auto overflow-x-hidden overscroll-contain touch-pan-y sm:absolute sm:left-auto sm:top-auto sm:bottom-auto sm:max-h-none sm:translate-x-0 sm:right-0 sm:mt-3 sm:w-[320px]">
                      <div className="absolute -top-12 -right-12 h-32 w-32 rounded-full bg-[color:var(--aqua)]/20 blur-3xl" />
                      <div className="absolute -bottom-16 left-6 h-36 w-36 rounded-full bg-[color:var(--blue)]/10 blur-3xl" />
                      <div className="relative p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:pb-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-xs font-semibold tracking-[0.3em] text-[color:var(--blue)]">
                              CENTRO DE INGESTA
                            </div>
                            <div className="mt-1 text-sm text-[color:var(--text-60)]">
                              Lanza procesos en segundo plano sin frenar tu flujo.
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {ingestActive && (
                              <div className="flex items-center gap-2 text-[11px] text-[color:var(--text-55)]">
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                {ingestProgress}% listo
                              </div>
                            )}
                            <button
                              type="button"
                              onClick={() => setIngestOpen(false)}
                              aria-label="Cerrar centro de ingesta"
                              title="Cerrar"
                              className="h-7 w-7 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] text-[color:var(--text-55)] transition hover:text-[color:var(--ink)] hover:border-[color:var(--aqua)]"
                            >
                              <X className="mx-auto h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>

                        {(["reputation"] as IngestJobKind[]).map((kind) => {
                          const job = ingestJobs[kind];
                          const busy =
                            ingestBusy[kind] ||
                            job?.status === "queued" ||
                            job?.status === "running";
                          const isError = job?.status === "error";
                          const isSuccess = job?.status === "success";
                          const label = "Ingesta reputación";
                          const detail = "Señales externas + sentimiento";
                          const metaBits: string[] = [];
                          const items = job?.meta?.items;
                          if (typeof items === "number") {
                            metaBits.push(`${items} items`);
                          }
                          const observations = job?.meta?.observations;
                          if (typeof observations === "number") {
                            metaBits.push(`${observations} observaciones`);
                          }
                          const sources = job?.meta?.sources;
                          if (typeof sources === "number") {
                            metaBits.push(`${sources} fuentes`);
                          }
                          const warning =
                            typeof job?.meta?.warning === "string" ? job.meta.warning : "";
                          const jobError = typeof job?.error === "string" ? job.error : "";
                          const metaLabel = metaBits.join(" · ");
                          const actionLabel = isError
                            ? "Reintentar ingesta"
                            : isSuccess
                              ? "Lanzar de nuevo"
                              : "Iniciar ingesta";
                          const actionDisabled = busy;
                          return (
                            <div
                              key={kind}
                              className="group relative w-full overflow-hidden rounded-[18px] border border-[color:var(--border-60)] bg-[color:var(--surface-80)] p-3 text-left"
                            >
                              <div className="absolute inset-0 opacity-0 transition group-hover:opacity-100" style={{ background: "radial-gradient(140px 60px at 0% 0%, rgba(45,204,205,0.18), transparent 60%)" }} />
                              <div className="relative flex items-start gap-3">
                                <div className="h-10 w-10 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] grid place-items-center">
                                  <Sparkles className="h-5 w-5 text-[color:var(--blue)]" />
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
                                  {isError && jobError && (
                                    <div className="mt-2 max-h-24 overflow-auto rounded-lg border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700 break-words">
                                      {jobError}
                                    </div>
                                  )}
                                </div>
                                <div className="flex items-center gap-2 text-xs">
                                  {busy && <Loader2 className="h-4 w-4 animate-spin text-[color:var(--blue)]" />}
                                  {isSuccess && !busy && (
                                    <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700">
                                      Completado
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

                              <div className="relative mt-3 flex items-center justify-end">
                                <button
                                  type="button"
                                  onClick={() => startIngest(kind)}
                                  disabled={actionDisabled}
                                  className="rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-55)] transition hover:bg-[color:var(--surface-60)] disabled:opacity-60"
                                >
                                  {actionLabel}
                                </button>
                              </div>
                            </div>
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
            </div>
            <div className="relative w-full sm:w-auto basis-full sm:basis-auto order-2 sm:order-none">
              <div className="group relative flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 rounded-[24px] sm:rounded-full border border-[color:var(--border-15)] bg-[color:var(--surface-10)] px-3 py-2 sm:px-2 sm:py-1 sm:pr-1 text-[color:var(--text-inverse-80)] shadow-[var(--shadow-pill)] backdrop-blur-sm w-full sm:w-auto">
                <div
                  className="absolute inset-0 opacity-0 transition group-hover:opacity-100"
                  style={{
                    background:
                      "radial-gradient(160px 80px at 0% 50%, rgba(45,204,205,0.22), transparent 65%)",
                  }}
                />
                <div className="relative flex items-center gap-3 min-w-0 w-full sm:w-auto">
                  <div className="h-8 w-8 rounded-full border border-[color:var(--border-15)] bg-[color:var(--surface-15)] grid place-items-center">
                    <Layers className="h-4 w-4 text-white" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-[8px] sm:text-[9px] uppercase tracking-[0.4em] sm:tracking-[0.32em] text-[color:var(--text-inverse-60)]">
                      Perfil activo
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className="text-[13px] sm:text-xs font-semibold text-white truncate max-w-[120px] sm:max-w-[160px] lg:max-w-[220px]"
                        title={primaryActiveLabel}
                      >
                        {primaryActiveLabel}
                      </span>
                      {extraActiveCount > 0 && (
                        <span className="rounded-full border border-[color:var(--border-15)] bg-[color:var(--surface-20)] px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-white/80">
                          +{extraActiveCount}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto sm:ml-auto">
                  {primaryActiveMeta ? (
                    <span
                      className="relative rounded-full border px-2.5 py-0.5 text-[10px] uppercase tracking-[0.18em] truncate max-w-[140px] sm:max-w-none"
                      style={{
                        color: primaryActiveMeta.tone,
                        borderColor: primaryActiveMeta.tone,
                      }}
                    >
                      {primaryActiveMeta.label}
                    </span>
                  ) : (
                    <span className="relative rounded-full border border-[color:var(--border-15)] px-2.5 py-0.5 text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-inverse-60)]">
                      Sin perfil
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={toggleProfileTemplates}
                    aria-label="Cambiar perfil"
                    title="Cambiar perfil"
                    className="relative w-full sm:w-auto rounded-full border border-[color:var(--border-15)] px-3 py-1 text-[9px] sm:text-[10px] uppercase tracking-[0.26em] sm:tracking-[0.24em] text-white transition hover:border-[color:var(--aqua)] hover:text-white active:scale-95"
                    style={{
                      background:
                        "linear-gradient(120deg, rgba(45, 204, 205, 0.3), rgba(0, 68, 129, 0.35))",
                    }}
                  >
                    <span className="sm:hidden">Cambiar</span>
                    <span className="hidden sm:inline">Cambiar perfil</span>
                  </button>
                </div>
              </div>
              {profileAppliedNote && (
                <span className="mt-2 sm:mt-0 sm:absolute sm:right-2 sm:-bottom-6 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-10)] px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-inverse-80)]">
                  {autoIngestNote
                    ? "Perfil aplicado · Ingesta automática"
                    : "Perfil aplicado"}
                </span>
              )}
              {profilesOpen && (
                <div className="fixed left-1/2 top-[calc(env(safe-area-inset-top)+6.5rem)] bottom-[calc(env(safe-area-inset-bottom)+5.5rem)] z-[70] mt-0 w-[92vw] max-w-[420px] -translate-x-1/2 rounded-[24px] border border-[color:var(--border-60)] bg-[color:var(--panel-strong)] shadow-[var(--shadow-lg)] backdrop-blur-xl overflow-y-auto overflow-x-hidden overscroll-contain touch-pan-y sm:absolute sm:left-auto sm:top-auto sm:bottom-auto sm:max-h-none sm:translate-x-0 sm:right-0 sm:mt-3 sm:w-[360px]">
                  <div className="absolute -top-10 right-6 h-24 w-24 rounded-full bg-[color:var(--aqua)]/20 blur-3xl" />
                  <div className="absolute -bottom-16 left-6 h-32 w-32 rounded-full bg-[color:var(--blue)]/20 blur-3xl" />
                  <div className="relative p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3">
                        <div className="h-10 w-10 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] grid place-items-center">
                          <Layers className="h-5 w-5 text-[color:var(--blue)]" />
                        </div>
                        <div className="flex-1">
                          <div className="text-[11px] font-semibold tracking-[0.35em] text-[color:var(--blue)]">
                            PERFIL
                          </div>
                          <div className="mt-1 text-sm text-[color:var(--text-60)]">
                            Elige el universo que quieres analizar.
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-60)]">
                          {selectionBadge}
                        </span>
                        <button
                          type="button"
                          onClick={() => setProfilesOpen(false)}
                          aria-label="Cerrar perfiles"
                          title="Cerrar"
                          className="h-7 w-7 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] text-[color:var(--text-55)] transition hover:text-[color:var(--ink)] hover:border-[color:var(--aqua)]"
                        >
                          <X className="mx-auto h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>

                    {templatesOpen && (
                      <>
                        <div className="mt-4 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-2">
                          <div className="flex items-center gap-3">
                            <div className="h-9 w-9 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] grid place-items-center">
                              <Sparkles className="h-4 w-4 text-[color:var(--aqua)]" />
                            </div>
                            <div className="text-[11px] text-[color:var(--text-60)]">
                              Las plantillas reemplazan los perfiles actuales. Si el caché está vacío,
                              lanzaremos una ingesta automática.
                            </div>
                          </div>
                        </div>

                        <div className="mt-4">
                          <label className="text-[10px] uppercase tracking-[0.28em] text-[color:var(--text-60)]">
                            Buscar perfil
                          </label>
                          <div className="relative mt-2">
                            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[color:var(--text-55)]" />
                            <input
                              value={profileQuery}
                              onChange={(event) => setProfileQuery(event.target.value)}
                              onKeyDown={(event) => {
                                if (event.key !== "Enter") return;
                                event.preventDefault();
                                if (!applyDisabled) {
                                  void applyProfiles();
                                }
                              }}
                              placeholder="Ej: banking, taylor, travel..."
                              className="w-full rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] py-2 pl-9 pr-3 text-sm text-[color:var(--ink)] placeholder:text-[color:var(--text-55)] outline-none transition focus:border-[color:var(--aqua)]"
                            />
                          </div>
                        </div>

                        <div className="mt-4">
                          <div className="text-[10px] uppercase tracking-[0.28em] text-[color:var(--text-60)]">
                            Sector
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                if (profileSelection.length) {
                                  setProfileSelection([]);
                                }
                                setSectorFocus("all");
                                setProfileCategoryWarning(null);
                              }}
                              className={`rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.2em] transition ${
                                (activeSectorKey ?? "all") === "all"
                                  ? "border-[color:var(--aqua)] bg-[color:var(--surface-70)] text-white"
                                  : "border-[color:var(--border-60)] text-[color:var(--text-60)]"
                              }`}
                            >
                              Todos
                            </button>
                            {sectorOptions.map((sector) => (
                              <button
                                key={sector.key}
                                type="button"
                                onClick={() => {
                                  if (profileSelection.length && sector.key !== selectedCategoryKey) {
                                    setProfileSelection([]);
                                  }
                                  setSectorFocus(sector.key);
                                  setProfileCategoryWarning(null);
                                }}
                                className={`rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.2em] transition ${
                                  activeSectorKey === sector.key
                                    ? "border-[color:var(--aqua)] bg-[color:var(--surface-70)] text-white"
                                    : "border-[color:var(--border-60)] text-[color:var(--text-60)]"
                                }`}
                              >
                                {sector.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      </>
                    )}

                    {templatesOpen && (activeSectorKey || selectedCategoryKey) && (
                      <div className="mt-2 text-[11px] text-[color:var(--text-60)]">
                        Sector activo:{" "}
                        <span className="font-semibold text-[color:var(--ink)]">
                          {categoryMetaByKey(activeSectorKey ?? selectedCategoryKey ?? "custom").label}
                        </span>
                      </div>
                    )}
                  </div>

                  {templatesOpen && (
                    <>
                      <div className="max-h-56 space-y-2 overflow-auto px-4 pb-4">
                        {profilesToRender.length ? (
                          profilesToRender.map((profile) => {
                            const category = categoryMeta(profile);
                            const selected = profileSelection.includes(profile);
                            const blocked =
                              activeSectorKey !== null &&
                              categoryKey(profile) !== activeSectorKey;
                            return (
                              <label
                                key={profile}
                                className={`group flex items-center justify-between gap-3 rounded-2xl border px-3 py-2 text-sm transition ${
                                  selected
                                    ? "border-[color:var(--aqua)] bg-[color:var(--gradient-chip)] text-[color:var(--ink)] shadow-[var(--shadow-pill)]"
                                    : "border-[color:var(--border-60)] bg-[color:var(--surface-80)] text-[color:var(--ink)] hover:shadow-[var(--shadow-soft)]"
                                } ${blocked ? "opacity-45 grayscale" : ""}`}
                                aria-disabled={blocked}
                                title={blocked ? "Bloqueado por sector" : undefined}
                              >
                                <div className="flex items-center gap-3">
                                  <input
                                    type="checkbox"
                                    className="h-4 w-4 accent-[color:var(--aqua)]"
                                    checked={selected}
                                    onChange={() => toggleProfileSelection(profile)}
                                    disabled={blocked}
                                  />
                                  <div className="min-w-0">
                                    <div className="truncate text-sm font-semibold">
                                      {formatProfileLabel(profile)}
                                    </div>
                                    <div className="truncate text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-55)]">
                                      {profile}
                                    </div>
                                  </div>
                                </div>
                                <span
                                  className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.18em]"
                                  style={{ color: category.tone, borderColor: category.tone }}
                                >
                                  {category.label}
                                </span>
                              </label>
                            );
                          })
                        ) : (
                          <div className="rounded-2xl border border-dashed border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-4 text-center text-xs text-[color:var(--text-60)]">
                            No hay perfiles para esa búsqueda.
                          </div>
                        )}
                      </div>

                      <div className="border-t border-[color:var(--border-60)] p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:pb-4 space-y-2">
                        <div className="flex items-center justify-end">
                          <button
                            type="button"
                            onClick={applyProfiles}
                            disabled={applyDisabled}
                            className="rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-solid)] px-4 py-1.5 text-xs font-semibold text-[color:var(--ink)] shadow-[var(--shadow-pill)] transition hover:shadow-[var(--shadow-pill-hover)] disabled:opacity-60"
                            style={{
                              background:
                                "linear-gradient(120deg, rgba(45, 204, 205, 0.22), rgba(0, 68, 129, 0.18), rgba(255, 255, 255, 0.95))",
                            }}
                          >
                            {profileBusy ? "Aplicando..." : "Aplicar"}
                          </button>
                        </div>
                        {profileCategoryWarning && (
                          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
                            {profileCategoryWarning}
                          </div>
                        )}
                        {emptySelectionHint && (
                          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
                            Selecciona al menos 1 plantilla para aplicar.
                          </div>
                        )}
                        {profileError && (
                          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                            {profileError}
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 order-1 w-auto sm:order-none">
              <div className="relative">
                <button
                  type="button"
                  onClick={toggleSettingsPanel}
                  aria-label="Configuración"
                  title="Configuración"
                  className="h-8 sm:h-9 px-2 sm:px-3 rounded-full flex items-center gap-2 border border-[color:var(--border-15)] bg-[color:var(--surface-10)] text-[color:var(--text-inverse-80)] transition hover:bg-[color:var(--surface-15)] hover:text-white"
                >
                  <SlidersHorizontal className="h-4 w-4" />
                  <span className="text-xs hidden sm:inline">Config</span>
                </button>
                {settingsOpen && (
                  <div className="settings-panel fixed left-1/2 top-[calc(env(safe-area-inset-top)+6.5rem)] bottom-[calc(env(safe-area-inset-bottom)+5.5rem)] z-[70] mt-0 w-[92vw] max-w-[520px] -translate-x-1/2 rounded-[26px] border border-[color:var(--border-60)] bg-[color:var(--panel-strong)] shadow-[var(--shadow-lg)] backdrop-blur-xl overflow-y-auto overflow-x-hidden overscroll-contain touch-pan-y sm:absolute sm:left-auto sm:top-auto sm:bottom-auto sm:max-h-none sm:translate-x-0 sm:right-0 sm:mt-3 sm:w-[420px]">
                    <div className="absolute -top-12 right-6 h-28 w-28 rounded-full bg-[color:var(--aqua)]/20 blur-3xl" />
                    <div className="absolute -bottom-16 left-10 h-32 w-32 rounded-full bg-[color:var(--blue)]/15 blur-3xl" />
                    <div className="relative p-4">
                      <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3">
                        <div className="h-10 w-10 rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] grid place-items-center">
                          <SlidersHorizontal className="h-5 w-5 text-[color:var(--blue)]" />
                        </div>
                        <div>
                          <div className="settings-header-title text-[11px] font-semibold tracking-[0.32em] text-[color:var(--blue)]">
                            CONFIGURACIÓN
                          </div>
                          <div className="settings-header-desc mt-1 text-sm text-[color:var(--text-60)]">
                            Personaliza las fuentes y credenciales de menciones.
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {settingsDirty && (
                          <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-amber-700">
                            Sin guardar
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => setSettingsOpen(false)}
                          aria-label="Cerrar configuración"
                          className="h-7 w-7 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-70)] text-[color:var(--text-55)] transition hover:text-[color:var(--ink)] hover:border-[color:var(--aqua)]"
                        >
                          <X className="mx-auto h-3.5 w-3.5" />
                        </button>
                      </div>
                      </div>
                      <div className="mt-3 flex items-center gap-2">
                        <span className="rounded-full border border-[color:var(--aqua)] bg-[color:var(--surface-70)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-white">
                          Menciones
                        </span>
                      </div>
                    </div>

                  <div className="max-h-none overflow-visible px-4 pb-24 space-y-3 sm:max-h-[60vh] sm:overflow-auto sm:pb-4">
                    {settingsGroups ? (
                      settingsGroups.map((group) => {
                        const isAdvanced = group.id === "advanced";
                        const advancedLogFields = isAdvanced
                          ? group.fields.filter((field) => ADVANCED_LOG_KEYS.has(field.key))
                          : [];
                        const advancedLogField = advancedLogFields.find(
                          (field) => field.key === "advanced.log_enabled",
                        );
                        const advancedLogControls = advancedLogFields.filter(
                          (field) => field.key !== "advanced.log_enabled",
                        );
                        const advancedExtraFields = isAdvanced
                          ? group.fields.filter((field) => !ADVANCED_LOG_KEYS.has(field.key))
                          : group.fields;
                        const fieldsToRender =
                          group.id === "sources_credentials"
                            ? []
                            : isAdvanced
                              ? advancedOpen
                                ? advancedExtraFields
                                : []
                              : group.fields;
                        return (
                          <div
                            key={group.id}
                            className="rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-80)] p-3"
                          >
                            <div className="settings-section-title text-[10px] uppercase tracking-[0.28em] text-[color:var(--text-55)]">
                              {group.label}
                            </div>
                            {group.description && (
                              <div className="settings-group-desc mt-1 text-[11px] text-[color:var(--text-60)]">
                                {group.description}
                              </div>
                            )}
                            {isAdvanced && advancedLogField && (
                              <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2">
                                <div className="min-w-0">
                                  <div className="settings-field-label text-xs font-semibold text-[color:var(--ink)]">
                                    {advancedLogField.label}
                                  </div>
                                  {advancedLogField.description && (
                                    <div className="settings-field-desc text-[10px] text-[color:var(--text-55)]">
                                      {advancedLogField.description}
                                    </div>
                                  )}
                                </div>
                                <button
                                  type="button"
                                  onClick={() =>
                                    updateSettingValue(
                                      advancedLogField.key,
                                      !Boolean(settingsDraft[advancedLogField.key])
                                    )
                                  }
                                  className={`settings-toggle ${
                                    settingsDraft[advancedLogField.key] ? "is-on" : "is-off"
                                  } relative inline-flex h-6 w-11 items-center rounded-full border transition ${
                                    settingsDraft[advancedLogField.key]
                                      ? "border-[color:var(--aqua)] bg-[color:var(--gradient-chip)]"
                                      : "border-[color:var(--border-60)] bg-[color:var(--surface-60)]"
                                  }`}
                                >
                                  <span
                                    className={`settings-toggle-knob inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
                                      settingsDraft[advancedLogField.key]
                                        ? "translate-x-5"
                                        : "translate-x-1"
                                    }`}
                                  />
                                </button>
                              </div>
                            )}
                            {isAdvanced && advancedLogControls.length > 0 && (
                              <div className="mt-3 space-y-3">
                                {advancedLogControls.map((field) => {
                                  const fieldValue = settingsDraft[field.key];
                                  return (
                                    <div
                                      key={field.key}
                                      className="flex items-center justify-between gap-3 rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2"
                                    >
                                      <div className="min-w-0">
                                        <div className="settings-field-label text-xs font-semibold text-[color:var(--ink)]">
                                          {field.label}
                                        </div>
                                        {field.description && (
                                          <div className="settings-field-desc text-[10px] text-[color:var(--text-55)]">
                                            {field.description}
                                          </div>
                                        )}
                                      </div>
                                      {field.type === "boolean" && (
                                        <button
                                          type="button"
                                          onClick={() =>
                                            updateSettingValue(field.key, !Boolean(fieldValue))
                                          }
                                          disabled={advancedLocked}
                                          className={`settings-toggle ${
                                            fieldValue ? "is-on" : "is-off"
                                          } relative inline-flex h-6 w-11 items-center rounded-full border transition ${
                                            fieldValue
                                              ? "border-[color:var(--aqua)] bg-[color:var(--gradient-chip)]"
                                              : "border-[color:var(--border-60)] bg-[color:var(--surface-60)]"
                                          }`}
                                        >
                                          <span
                                            className={`settings-toggle-knob inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
                                              fieldValue ? "translate-x-5" : "translate-x-1"
                                            }`}
                                          />
                                        </button>
                                      )}
                                      {(field.type === "string" ||
                                        field.type === "secret" ||
                                        field.type === "number") && (
                                        <input
                                          type={
                                            field.type === "secret"
                                              ? "password"
                                              : field.type === "number"
                                                ? "number"
                                                : "text"
                                          }
                                          value={String(fieldValue ?? "")}
                                          onChange={(event) => {
                                            const rawValue = event.target.value;
                                            if (field.type === "number") {
                                              const parsed = Number(rawValue);
                                              updateSettingValue(
                                                field.key,
                                                Number.isNaN(parsed) ? 0 : parsed
                                              );
                                              return;
                                            }
                                            updateSettingValue(field.key, rawValue);
                                          }}
                                          placeholder={field.placeholder ?? ""}
                                          disabled={advancedLocked}
                                          className="w-40 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-60)] px-3 py-1 text-xs text-[color:var(--ink)] disabled:opacity-50"
                                        />
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                            {isAdvanced && (
                              <div className="mt-3 flex items-center justify-between rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2">
                                <div className="settings-field-desc text-[11px] text-[color:var(--text-60)]">
                                  Mostrar opciones avanzadas
                                </div>
                                <button
                                  type="button"
                                  onClick={() => setAdvancedOpen((prev) => !prev)}
                                  className={`settings-toggle ${
                                    advancedOpen ? "is-on" : "is-off"
                                  } relative inline-flex h-6 w-11 items-center rounded-full border transition ${
                                    advancedOpen
                                      ? "border-[color:var(--aqua)] bg-[color:var(--gradient-chip)]"
                                      : "border-[color:var(--border-60)] bg-[color:var(--surface-60)]"
                                  }`}
                                >
                                  <span
                                    className={`settings-toggle-knob inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
                                      advancedOpen ? "translate-x-5" : "translate-x-1"
                                    }`}
                                  />
                                </button>
                              </div>
                            )}
                            {group.id === "sources_credentials" && (
                              <div className="mt-3 space-y-3">
                                {credentialSourceRows.map((row) => {
                                  const toggleField = settingsFieldMap.get(row.toggleKey);
                                  if (!toggleField) return null;
                                  const enabled = Boolean(settingsDraft[row.toggleKey]);
                                  const missing = row.keyKeys.filter((key) => {
                                    const value = settingsDraft[key];
                                    return !String(value ?? "").trim();
                                  });
                                  return (
                                    <div
                                      key={row.id}
                                      className="rounded-2xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2"
                                    >
                                      <div className="flex items-center justify-between gap-3">
                                        <div className="min-w-0">
                                          <div className="settings-field-label text-xs font-semibold text-[color:var(--ink)]">
                                            {toggleField.label}
                                          </div>
                                          {toggleField.description && (
                                            <div className="settings-field-desc text-[10px] text-[color:var(--text-55)]">
                                              {toggleField.description}
                                            </div>
                                          )}
                                        </div>
                                        <button
                                          type="button"
                                          onClick={() =>
                                            updateSettingValue(row.toggleKey, !enabled)
                                          }
                                          className={`settings-toggle ${
                                            enabled ? "is-on" : "is-off"
                                          } relative inline-flex h-6 w-11 items-center rounded-full border transition ${
                                            enabled
                                              ? "border-[color:var(--aqua)] bg-[color:var(--gradient-chip)]"
                                              : "border-[color:var(--border-60)] bg-[color:var(--surface-60)]"
                                          }`}
                                        >
                                          <span
                                            className={`settings-toggle-knob inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
                                              enabled ? "translate-x-5" : "translate-x-1"
                                            }`}
                                          />
                                        </button>
                                      </div>
                                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                        {row.keyKeys.map((key) => {
                                          const field = settingsFieldMap.get(key);
                                          if (!field) return null;
                                          if (field.type === "select" && field.options?.length) {
                                            const value = String(
                                              settingsDraft[key] ?? field.options[0] ?? ""
                                            );
                                            return (
                                              <select
                                                key={key}
                                                value={value}
                                                onChange={(event) =>
                                                  updateSettingValue(key, event.target.value)
                                                }
                                                className="w-full rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-60)] px-3 py-1 text-xs text-[color:var(--ink)]"
                                              >
                                                {field.options.map((option) => (
                                                  <option key={option} value={option}>
                                                    {option}
                                                  </option>
                                                ))}
                                              </select>
                                            );
                                          }
                                          const inputType =
                                            field.type === "secret"
                                              ? "password"
                                              : field.type === "number"
                                                ? "number"
                                                : "text";
                                          return (
                                            <input
                                              key={key}
                                              type={inputType}
                                              value={String(settingsDraft[key] ?? "")}
                                              onChange={(event) =>
                                                updateSettingValue(key, event.target.value)
                                              }
                                              placeholder={field.placeholder ?? field.label}
                                              className="w-full rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-60)] px-3 py-1 text-xs text-[color:var(--ink)]"
                                            />
                                          );
                                        })}
                                      </div>
                                      {enabled && missing.length > 0 && (
                                        <div className="mt-2 text-[10px] text-rose-500">
                                          Añade la API Key o desactiva la fuente para continuar.
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                                {credentialSourceRows.length === 0 && (
                                  <div className="text-[11px] text-[color:var(--text-55)]">
                                    No hay fuentes con credenciales configuradas.
                                  </div>
                                )}
                              </div>
                            )}
                            {isAdvanced && advancedOpen && (
                              <div className="mt-3 rounded-xl border border-dashed border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2">
                                <div className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-55)]">
                                  Añadir variable
                                </div>
                                <div className="mt-2 flex flex-wrap items-center gap-2">
                                  <select
                                    value={advancedKey}
                                    onChange={(event) => setAdvancedKey(event.target.value)}
                                    disabled={advancedLocked}
                                    className="flex-1 min-w-[180px] rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-60)] px-3 py-1 text-xs text-[color:var(--ink)] disabled:opacity-50"
                                  >
                                    <option value="">Selecciona variable</option>
                                    {availableAdvancedOptions.map((option) => (
                                      <option key={option} value={option}>
                                        {option}
                                      </option>
                                    ))}
                                  </select>
                                  <input
                                    type="text"
                                    value={advancedValue}
                                    onChange={(event) => setAdvancedValue(event.target.value)}
                                    placeholder="valor"
                                    disabled={advancedLocked}
                                    className="flex-1 min-w-[140px] rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-60)] px-3 py-1 text-xs text-[color:var(--ink)] disabled:opacity-50"
                                  />
                                  <button
                                    type="button"
                                    onClick={addAdvancedSetting}
                                    disabled={advancedLocked}
                                    className="rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-solid)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-[color:var(--ink)] disabled:opacity-50"
                                  >
                                    Añadir
                                  </button>
                                </div>
                                {availableAdvancedOptions.length > 0 && (
                                  <div className="mt-2 text-[10px] text-[color:var(--text-55)]">
                                    {availableAdvancedOptions.length} variables disponibles.
                                  </div>
                                )}
                                {advancedLocked && (
                                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-60)] px-3 py-2 text-[10px] text-[color:var(--text-55)]">
                                    <span>Activa los logs para editar variables avanzadas.</span>
                                    <button
                                      type="button"
                                      onClick={() =>
                                        updateSettingValue("advanced.log_enabled", true)
                                      }
                                      className="rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-solid)] px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-[color:var(--ink)]"
                                    >
                                      Activar logs
                                    </button>
                                  </div>
                                )}
                                {!availableAdvancedOptions.length && (
                                  <div className="mt-2 text-[10px] text-[color:var(--text-55)]">
                                    No hay variables adicionales disponibles.
                                  </div>
                                )}
                                {advancedError && (
                                  <div className="mt-2 text-[10px] text-rose-500">
                                    {advancedError}
                                  </div>
                                )}
                              </div>
                            )}
                            <div className="mt-3 space-y-3">
                              {fieldsToRender.map((field) => {
                                const fieldValue = settingsDraft[field.key];
                                const fieldDisabled =
                                  isAdvanced &&
                                  field.key !== "advanced.log_enabled" &&
                                  advancedLocked;
                                return (
                                  <div
                                    key={field.key}
                                    className="flex items-center justify-between gap-3 rounded-xl border border-[color:var(--border-60)] bg-[color:var(--surface-70)] px-3 py-2"
                                  >
                                    <div className="min-w-0">
                                      <div className="settings-field-label text-xs font-semibold text-[color:var(--ink)]">
                                        {field.label}
                                      </div>
                                      {field.description && (
                                        <div className="settings-field-desc text-[10px] text-[color:var(--text-55)]">
                                          {field.description}
                                        </div>
                                      )}
                                    </div>
                                    {field.type === "boolean" && (
                                      <button
                                        type="button"
                                        onClick={() =>
                                          updateSettingValue(field.key, !Boolean(fieldValue))
                                        }
                                        disabled={fieldDisabled}
                                        className={`settings-toggle ${
                                          fieldValue ? "is-on" : "is-off"
                                        } relative inline-flex h-6 w-11 items-center rounded-full border transition ${
                                          fieldValue
                                            ? "border-[color:var(--aqua)] bg-[color:var(--gradient-chip)]"
                                            : "border-[color:var(--border-60)] bg-[color:var(--surface-60)]"
                                        }`}
                                      >
                                        <span
                                          className={`settings-toggle-knob inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
                                            fieldValue ? "translate-x-5" : "translate-x-1"
                                          }`}
                                        />
                                      </button>
                                    )}
                                    {field.type === "select" && (
                                      <select
                                        value={String(fieldValue ?? "")}
                                        onChange={(event) =>
                                          updateSettingValue(field.key, event.target.value)
                                        }
                                        disabled={fieldDisabled}
                                        className="rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-60)] px-3 py-1 text-xs text-[color:var(--ink)]"
                                      >
                                        {(field.options ?? []).map((option) => {
                                          const isLanguage = field.key === "language.preference";
                                          const label = isLanguage
                                            ? LANGUAGE_LABELS[option] ?? option
                                            : option;
                                          return (
                                            <option key={option} value={option}>
                                              {label}
                                            </option>
                                          );
                                        })}
                                      </select>
                                    )}
                                    {(field.type === "string" ||
                                      field.type === "secret" ||
                                      field.type === "number") && (
                                      <div className="flex items-center gap-2">
                                        <input
                                          type={
                                            field.type === "secret"
                                              ? "password"
                                              : field.type === "number"
                                                ? "number"
                                                : "text"
                                          }
                                          value={String(fieldValue ?? "")}
                                          onChange={(event) => {
                                            const rawValue = event.target.value;
                                            if (field.type === "number") {
                                              const parsed = Number(rawValue);
                                              updateSettingValue(
                                                field.key,
                                                Number.isNaN(parsed) ? 0 : parsed
                                              );
                                              return;
                                            }
                                            updateSettingValue(field.key, rawValue);
                                          }}
                                          placeholder={field.placeholder ?? ""}
                                          disabled={fieldDisabled}
                                          className="w-40 rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-60)] px-3 py-1 text-xs text-[color:var(--ink)] disabled:opacity-50"
                                        />
                                        {isAdvanced && (
                                          <button
                                            type="button"
                                            onClick={() => updateSettingValue(field.key, "")}
                                            disabled={fieldDisabled}
                                            className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-55)] hover:text-rose-500"
                                          >
                                            Quitar
                                          </button>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                              {isAdvanced &&
                                advancedOpen &&
                                advancedExtraFields.length === 0 && (
                                <div className="text-[11px] text-[color:var(--text-55)]">
                                  No hay variables avanzadas configuradas.
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="rounded-2xl border border-dashed border-[color:var(--border-60)] bg-[color:var(--surface-80)] px-3 py-6 text-center text-xs text-[color:var(--text-55)]">
                        {settingsError ? settingsError : "Cargando configuración..."}
                      </div>
                    )}
                  </div>
                  {settingsError && settingsGroups && (
                    <div className="px-4 pb-4">
                      <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                        {settingsError}
                      </div>
                    </div>
                  )}

                  <div className="sticky bottom-0 z-10 border-t border-[color:var(--border-60)] bg-[color:var(--panel-strong)]/95 backdrop-blur p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:static sm:backdrop-blur-none sm:bg-transparent sm:pb-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={resetSettingsDraft}
                        disabled={!settingsDirty || settingsBusy}
                        className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-55)] disabled:opacity-50"
                      >
                        Deshacer cambios
                      </button>
                      <button
                        type="button"
                        onClick={resetSettingsToDefault}
                        disabled={settingsBusy}
                        className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-55)] hover:text-[color:var(--ink)]"
                      >
                        Volver a valores por defecto
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      {hasCredentialIssues && (
                        <span className="text-[11px] text-rose-500">
                          Completa credenciales o desactiva la fuente.
                        </span>
                      )}
                      {settingsSaved && (
                        <span className="text-[11px] text-[color:var(--text-60)]">
                          Guardado
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={saveSettings}
                        disabled={settingsBusy || !settingsDirty || hasCredentialIssues}
                        className="rounded-full border border-[color:var(--border-60)] bg-[color:var(--surface-solid)] px-4 py-1.5 text-xs font-semibold text-[color:var(--ink)] shadow-[var(--shadow-pill)] transition hover:shadow-[var(--shadow-pill-hover)] disabled:opacity-60"
                        style={{
                          background:
                            "linear-gradient(120deg, rgba(45, 204, 205, 0.22), rgba(0, 68, 129, 0.18), rgba(255, 255, 255, 0.95))",
                        }}
                      >
                        {settingsBusy ? "Guardando..." : "Guardar"}
                      </button>
                    </div>
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
                className="h-8 w-8 sm:h-9 sm:w-9 rounded-full grid place-items-center border border-[color:var(--border-15)] bg-[color:var(--surface-10)] text-[color:var(--text-inverse-80)] transition hover:bg-[color:var(--surface-15)] hover:text-white active:scale-95"
                suppressHydrationWarning
              >
                {!themeReady ? (
                  <Moon className="h-4 w-4" />
                ) : theme === "ambient-light" ? (
                  <Moon className="h-4 w-4" />
                ) : (
                  <Sun className="h-4 w-4" />
                )}
              </button>
            </div>

          </div>
        </div>
      </header>

      {/* Layout principal */}
      <div className="mx-auto max-w-7xl px-4 pt-6 pb-24 lg:py-6 grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-6">
        {/* Barra lateral */}
        <aside
          className="hidden lg:block h-fit rounded-[var(--radius)] border backdrop-blur-xl"
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

      {/* Tab bar mobile */}
      <div className="lg:hidden fixed bottom-0 left-0 right-0 z-50">
        <div className="mx-auto max-w-7xl px-4 pb-[calc(env(safe-area-inset-bottom,0px)+12px)] pt-3">
          <div
            className="rounded-[24px] border backdrop-blur-xl overflow-hidden"
            style={{
              background: "var(--panel)",
              borderColor: "var(--border-60)",
              boxShadow: "var(--shadow-lg)",
            }}
          >
            <nav className="grid grid-flow-col auto-cols-fr">
              {nav.map((item) => {
                const active = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={`mobile-${item.href}`}
                    href={item.href}
                    className={
                      "flex flex-col items-center justify-center gap-1 px-3 py-3 text-[10px] uppercase tracking-[0.24em] transition " +
                      (active
                        ? "text-white"
                        : "text-[color:var(--text-60)] hover:text-white")
                    }
                    style={
                      active
                        ? {
                            background: "var(--nav-active-gradient)",
                            boxShadow: "var(--nav-active-shadow)",
                          }
                        : undefined
                    }
                  >
                    <Icon
                      className={
                        active
                          ? "h-5 w-5 text-white"
                          : "h-5 w-5 text-[color:var(--blue)]"
                      }
                    />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      </div>
    </div>
  );
}
