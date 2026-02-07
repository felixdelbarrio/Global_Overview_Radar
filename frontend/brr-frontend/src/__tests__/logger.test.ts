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

  it("logs without meta using console method", async () => {
    const infoSpy = vi.spyOn(console, "info").mockImplementation(() => {});
    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "false",
    });

    logger.info("solo texto");

    expect(infoSpy).toHaveBeenCalledWith(expect.stringContaining("solo texto"));
  });

  it("logs warn with meta resolved from function", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "false",
    });

    logger.warn("aviso", () => ({ ok: true }));

    expect(warnSpy).toHaveBeenCalled();
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

  it("falls back to fetch when sendBeacon is missing", async () => {
    const originalBeacon = navigator.sendBeacon;
    Object.defineProperty(navigator, "sendBeacon", {
      value: undefined,
      configurable: true,
    });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchMock as typeof fetch;

    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });

    logger.info("sin beacon");
    window.dispatchEvent(new Event("pagehide"));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalled();

    Object.defineProperty(navigator, "sendBeacon", {
      value: originalBeacon,
      configurable: true,
    });
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

  it("flushes queued logs on timer when toFile is enabled", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchMock as typeof fetch;

    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });

    logger.info("timer");
    vi.advanceTimersByTime(1100);
    await Promise.resolve();

    expect(fetchMock).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("flushes when buffer reaches max size", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchMock as typeof fetch;

    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });

    for (let i = 0; i < 55; i += 1) {
      logger.info(`msg-${i}`);
    }

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalled();
  });

  it("flushes when document becomes hidden", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchMock as typeof fetch;

    const logger = await loadLogger({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_DEBUG: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });

    logger.info("hidden");
    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalled();
  });
});
