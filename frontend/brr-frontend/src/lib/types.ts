/** Tipos compartidos del dominio para el frontend. */

export type ReputationItemOverride = {
  geo?: string | null;
  sentiment?: "positive" | "neutral" | "negative" | null;
  updated_at?: string | null;
  note?: string | null;
};

export type ReputationItem = {
  id: string;
  source: string;
  geo?: string | null;
  actor?: string | null;
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
  manual_override?: ReputationItemOverride | null;
};

export type ReputationCacheDocument = {
  generated_at: string;
  config_hash: string;
  sources_enabled: string[];
  items: ReputationItem[];
  market_ratings?: MarketRating[];
  market_ratings_history?: MarketRating[];
  stats: {
    count: number;
    note?: string | null;
  };
};

export type MarketRating = {
  source: string;
  actor?: string | null;
  geo?: string | null;
  app_id?: string | null;
  package_id?: string | null;
  rating: number;
  rating_count?: number | null;
  url?: string | null;
  name?: string | null;
  collected_at?: string | null;
};

export type ActorPrincipalMeta = {
  canonical: string;
  names?: string[];
  aliases?: string[];
};

export type ReputationMeta = {
  actor_principal?: ActorPrincipalMeta | null;
  geos?: string[];
  otros_actores_por_geografia?: Record<string, string[]>;
  otros_actores_globales?: string[];
  sources_enabled?: string[];
  sources_available?: string[];
  source_counts?: Record<string, number>;
  cache_available?: boolean;
  market_ratings?: MarketRating[];
  market_ratings_history?: MarketRating[];
  ui_show_comparisons?: boolean;
  profiles_active?: string[];
  profile_key?: string;
  profile_source?: string;
};

export type IngestJobKind = "reputation";
export type IngestJobStatus = "queued" | "running" | "success" | "error";

export type IngestJob = {
  id: string;
  kind: IngestJobKind;
  status: IngestJobStatus;
  progress: number;
  stage?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  meta?: Record<string, unknown> | null;
};
