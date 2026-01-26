export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";

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

export type EvolutionPoint = {
  date: string; // YYYY-MM-DD
  open: number;
  new: number;
  closed: number;
};