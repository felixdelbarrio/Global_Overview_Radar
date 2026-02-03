import type { IngestJob, IngestJobKind } from "@/lib/types";

export const INGEST_SUCCESS_EVENT = "gor:ingest:success";
export const INGEST_STARTED_EVENT = "gor:ingest:started";

export type IngestSuccessDetail = {
  kind: IngestJobKind;
  finished_at?: string | null;
};

export type IngestStartedDetail = IngestJob;

export const dispatchIngestSuccess = (detail: IngestSuccessDetail) => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INGEST_SUCCESS_EVENT, { detail }));
};

export const dispatchIngestStarted = (detail: IngestStartedDetail) => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INGEST_STARTED_EVENT, { detail }));
};
