/** Tipos compartidos del dominio para el frontend. */

/** Severidad estandarizada de incidencias. */
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";

/** Resumen de KPIs agregados expuesto por la API. */
export type Kpis = {
  open_total: number;
  open_by_severity: Record<Severity, number>;

  new_total: number;
  new_by_severity: Record<Severity, number>;
  new_masters: number;

  closed_total: number;
  closed_by_severity: Record<Severity, number>;

  mean_resolution_days_overall: number | null;
  mean_resolution_days_by_severity: Partial<Record<Severity, number>>;

  open_over_threshold_pct: number;
  open_over_threshold_list: string[];
};

/** Punto de la serie temporal (evolucion diaria). */
export type EvolutionPoint = {
  /** Fecha en formato YYYY-MM-DD. */
  date: string;
  /** Incidencias abiertas en la fecha. */
  open: number;
  /** Incidencias nuevas en la fecha. */
  new: number;
  /** Incidencias cerradas en la fecha. */
  closed: number;
};

export type ReputationItem = {
  id: string;
  source: string;
  geo?: string | null;
  competitor?: string | null;
  language?: string | null;
  published_at?: string | null;
  collected_at?: string | null;
  author?: string | null;
  url?: string | null;
  title?: string | null;
  text?: string | null;
  signals?: Record<string, unknown>;
  sentiment?: "positive" | "neutral" | "negative" | null;
  aspects?: string[];
};

export type ReputationCacheDocument = {
  generated_at: string;
  config_hash: string;
  sources_enabled: string[];
  items: ReputationItem[];
  stats: {
    count: number;
    note?: string | null;
  };
};
