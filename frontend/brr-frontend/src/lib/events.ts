import type { IngestJobKind } from "@/lib/types";

export const INGEST_SUCCESS_EVENT = "gor:ingest:success";

export type IngestSuccessDetail = {
  kind: IngestJobKind;
  finished_at?: string | null;
};

export const dispatchIngestSuccess = (detail: IngestSuccessDetail) => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INGEST_SUCCESS_EVENT, { detail }));
};
