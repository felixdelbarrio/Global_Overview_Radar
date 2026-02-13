import type { IngestJob, IngestJobKind } from "@/lib/types";
import { clearApiCache } from "@/lib/api";

export const INGEST_SUCCESS_EVENT = "gor:ingest:success";
export const INGEST_STARTED_EVENT = "gor:ingest:started";
export const PROFILE_CHANGED_EVENT = "gor:profile:changed";
export const SETTINGS_CHANGED_EVENT = "gor:settings:changed";

export type IngestSuccessDetail = {
  kind: IngestJobKind;
  finished_at?: string | null;
};

export type IngestStartedDetail = IngestJob;

export type ProfileChangedDetail = {
  source: string;
  profiles: string[];
  profile_key?: string;
};

export type SettingsChangedDetail = {
  updated_at?: string | null;
};

export const dispatchIngestSuccess = (detail: IngestSuccessDetail) => {
  if (typeof window === "undefined") return;
  clearApiCache();
  window.dispatchEvent(new CustomEvent(INGEST_SUCCESS_EVENT, { detail }));
};

export const dispatchIngestStarted = (detail: IngestStartedDetail) => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INGEST_STARTED_EVENT, { detail }));
};

export const dispatchProfileChanged = (detail: ProfileChangedDetail) => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(PROFILE_CHANGED_EVENT, { detail }));
};

export const dispatchSettingsChanged = (detail: SettingsChangedDetail = {}) => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(SETTINGS_CHANGED_EVENT, { detail }));
};
