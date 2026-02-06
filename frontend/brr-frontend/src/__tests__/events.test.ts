/** Tests de eventos custom. */

import { describe, expect, it, vi } from "vitest";
import {
  dispatchIngestStarted,
  dispatchIngestSuccess,
  dispatchProfileChanged,
  dispatchSettingsChanged,
  INGEST_STARTED_EVENT,
  INGEST_SUCCESS_EVENT,
  PROFILE_CHANGED_EVENT,
  SETTINGS_CHANGED_EVENT,
} from "@/lib/events";

describe("events", () => {
  it("dispatches ingest/profile/settings events", () => {
    const spy = vi.spyOn(window, "dispatchEvent");

    dispatchIngestStarted({
      id: "job-1",
      kind: "reputation",
      status: "queued",
      progress: 0,
    });
    dispatchIngestSuccess({ kind: "reputation", finished_at: "2025-01-01T00:00:00Z" });
    dispatchProfileChanged({ source: "default", profiles: ["banking"], profile_key: "banking" });
    dispatchSettingsChanged({ updated_at: "2025-01-02T00:00:00Z" });

    const calls = spy.mock.calls.map(([event]) => (event as CustomEvent).type);
    expect(calls).toContain(INGEST_STARTED_EVENT);
    expect(calls).toContain(INGEST_SUCCESS_EVENT);
    expect(calls).toContain(PROFILE_CHANGED_EVENT);
    expect(calls).toContain(SETTINGS_CHANGED_EVENT);
  });

  it("no-ops when window is undefined", () => {
    const originalWindow = globalThis.window;
    Object.defineProperty(globalThis, "window", {
      value: undefined,
      configurable: true,
    });

    expect(() =>
      dispatchIngestStarted({
        id: "job-2",
        kind: "reputation",
        status: "queued",
        progress: 0,
      })
    ).not.toThrow();
    expect(() => dispatchIngestSuccess({ kind: "reputation" })).not.toThrow();
    expect(() =>
      dispatchProfileChanged({ source: "default", profiles: ["banking"] })
    ).not.toThrow();
    expect(() => dispatchSettingsChanged()).not.toThrow();

    Object.defineProperty(globalThis, "window", {
      value: originalWindow,
      configurable: true,
    });
  });
});
