/** Tests de logger (frontend). */

import { afterEach, describe, expect, it, vi } from "vitest";

const originalEnv = { ...process.env };

const loadLogger = async (env: Record<string, string | undefined>) => {
  vi.resetModules();
  process.env = { ...originalEnv, ...env };
  return (await import("@/lib/logger")).logger;
};

afterEach(() => {
  process.env = { ...originalEnv };
  vi.restoreAllMocks();
});

describe("logger", () => {
  it("skips logging when disabled", async () => {
    const infoSpy = vi.spyOn(console, "info").mockImplementation(() => {});
    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "false",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "false",
    });

    logger.info("apagado");

    expect(infoSpy).not.toHaveBeenCalled();
  });

  it("skips debug when debug is disabled", async () => {
    const debugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});
    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "false",
      NEXT_PUBLIC_LOG_TO_FILE: "false",
    });

    logger.debug("silencio");

    expect(debugSpy).not.toHaveBeenCalled();
  });

  it("logs to console when enabled and not writing to file", async () => {
    const debugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});
    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "false",
    });

    logger.debug("hola", { ok: true });

    expect(debugSpy).toHaveBeenCalled();
  });

  it("buffers and sends logs to file when enabled", async () => {
    const sendBeacon = vi.fn(() => true);
    Object.defineProperty(navigator, "sendBeacon", {
      value: sendBeacon,
      configurable: true,
    });

    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });

    logger.info("archivo");
    window.dispatchEvent(new Event("pagehide"));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sendBeacon).toHaveBeenCalled();
  });

  it("falls back to fetch when sendBeacon fails and sanitizes meta", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchMock as typeof fetch;

    const sendBeacon = vi.fn(() => false);
    Object.defineProperty(navigator, "sendBeacon", {
      value: sendBeacon,
      configurable: true,
    });

    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });

    const circular: { self?: unknown } = {};
    circular.self = circular;

    logger.warn("circular", circular);
    window.dispatchEvent(new Event("pagehide"));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sendBeacon).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalled();
  });
});
