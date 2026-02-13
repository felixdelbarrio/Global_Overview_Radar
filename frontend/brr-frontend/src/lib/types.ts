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
  ui_show_dashboard_responses?: boolean;
  profiles_active?: string[];
  profile_key?: string;
  profile_source?: string;
};

export type MarketRecurringOpinion = {
  id: string;
  source: string;
  geo: string;
  sentiment: string;
  published_at?: string | null;
  title?: string;
  url?: string | null;
  excerpt?: string;
};

export type MarketRecurringAuthor = {
  author: string;
  opinions_count: number;
  sentiments: Record<string, number>;
  last_seen?: string | null;
  opinions: MarketRecurringOpinion[];
};

export type MarketFeatureEvidence = {
  id: string;
  source: string;
  geo: string;
  sentiment: string;
  published_at?: string | null;
  title?: string;
  excerpt?: string;
  url?: string | null;
};

export type MarketPenalizedFeature = {
  feature: string;
  key: string;
  count: number;
  evidence: MarketFeatureEvidence[];
};

export type MarketSourceFriction = {
  source: string;
  total: number;
  negative: number;
  positive: number;
  neutral: number;
  negative_ratio: number;
  top_features: Array<{ feature: string; count: number }>;
};

export type MarketAlert = {
  id: string;
  severity: "critical" | "high" | "medium" | "low" | string;
  title: string;
  summary: string;
  geo?: string | null;
  source?: string | null;
  evidence_ids?: string[];
};

export type MarketNewsletterEdition = {
  geo: string;
  subject: string;
  preview: string;
  markdown: string;
  actions: string[];
};

export type ResponseSummaryTotals = {
  opinions_total: number;
  answered_total: number;
  answered_ratio: number;
  answered_positive: number;
  answered_neutral: number;
  answered_negative: number;
  unanswered_positive: number;
  unanswered_neutral: number;
  unanswered_negative: number;
};

export type ResponseSummaryActor = {
  actor: string;
  actor_type: "principal" | "secondary" | "unknown" | string;
  answered: number;
  answered_positive: number;
  answered_neutral: number;
  answered_negative: number;
};

export type ResponseSummaryRepeatedReply = {
  reply_text: string;
  count: number;
  actors: Array<{ actor: string; count: number }>;
  sentiments: Record<string, number>;
  sample_item_ids: string[];
};

export type ResponseSummaryAnsweredItem = {
  id: string;
  source: string;
  geo: string;
  sentiment: string;
  actor?: string | null;
  actor_canonical?: string | null;
  responder_actor?: string | null;
  responder_actor_type?: string | null;
  reply_text: string;
  reply_excerpt?: string | null;
  reply_author?: string | null;
  replied_at?: string | null;
  published_at?: string | null;
  title?: string;
  url?: string | null;
};

export type ReputationResponsesSummary = {
  generated_at?: string;
  filters?: {
    entity?: string;
    actor?: string | null;
    geo?: string;
    sentiment?: string;
    sources?: string[];
    from_date?: string | null;
    to_date?: string | null;
    detail_limit?: number;
  };
  totals: ResponseSummaryTotals;
  actor_breakdown: ResponseSummaryActor[];
  repeated_replies: ResponseSummaryRepeatedReply[];
  answered_items: ResponseSummaryAnsweredItem[];
};

export type MarketInsightsResponse = {
  generated_at: string;
  principal_actor: string;
  comparisons_enabled: boolean;
  filters: {
    geo: string;
    from_date?: string | null;
    to_date?: string | null;
    sources: string[];
  };
  kpis: {
    total_mentions: number;
    negative_mentions: number;
    negative_ratio: number;
    positive_mentions: number;
    neutral_mentions: number;
    unique_authors: number;
    recurring_authors: number;
    average_sentiment_score?: number | null;
  };
  daily_volume: Array<{ date: string; count: number }>;
  geo_summary: Array<{
    geo: string;
    total: number;
    negative: number;
    positive: number;
    neutral: number;
    negative_ratio: number;
    share: number;
  }>;
  recurring_authors: MarketRecurringAuthor[];
  top_penalized_features: MarketPenalizedFeature[];
  source_friction: MarketSourceFriction[];
  alerts: MarketAlert[];
  responses?: ReputationResponsesSummary;
  newsletter_by_geo: MarketNewsletterEdition[];
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
