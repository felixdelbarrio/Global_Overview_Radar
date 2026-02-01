type LogLevel = "debug" | "info" | "warn" | "error";

type LoggerConfig = {
  enabled: boolean;
  toFile: boolean;
  debug: boolean;
};

type LogEntry = {
  level: LogLevel;
  message: string;
  meta?: unknown;
  timestamp: string;
};

type LogMeta = unknown | (() => unknown);

function parseBool(value: string | undefined): boolean {
  return (value ?? "").trim().toLowerCase() === "true";
}

function readConfig(): LoggerConfig {
  return {
    enabled: parseBool(process.env.NEXT_PUBLIC_LOG_ENABLED),
    toFile: parseBool(process.env.NEXT_PUBLIC_LOG_TO_FILE),
    debug: parseBool(process.env.NEXT_PUBLIC_LOG_DEBUG),
  };
}

const CONFIG = readConfig();
const HAS_WINDOW = typeof window !== "undefined";
const BUFFER: LogEntry[] = [];
const MAX_BUFFER = 50;
const FLUSH_INTERVAL_MS = 1000;
let flushTimer: number | null = null;
let flushing = false;

function shouldLog(level: LogLevel, config: LoggerConfig): boolean {
  if (!config.enabled) return false;
  if (level === "debug" && !config.debug) return false;
  return true;
}

function safeSerialize(entries: LogEntry[]): string {
  try {
    return JSON.stringify({ entries });
  } catch {
    const sanitized = entries.map((entry) => ({
      ...entry,
      meta: entry.meta === undefined ? null : String(entry.meta),
    }));
    return JSON.stringify({ entries: sanitized });
  }
}

async function sendBatch(entries: LogEntry[], useBeacon: boolean): Promise<void> {
  if (!HAS_WINDOW || entries.length === 0) return;
  const payload = safeSerialize(entries);

  if (useBeacon && "sendBeacon" in navigator) {
    try {
      const blob = new Blob([payload], { type: "application/json" });
      const ok = navigator.sendBeacon("/api/log", blob);
      if (ok) return;
    } catch {
      // Fallback to fetch below.
    }
  }

  try {
    await fetch("/api/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: useBeacon,
    });
  } catch {
    // Swallow logging errors to avoid breaking UX.
  }
}

function scheduleFlush(): void {
  if (!HAS_WINDOW || flushTimer !== null) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = null;
    void flush(false);
  }, FLUSH_INTERVAL_MS);
}

async function flush(useBeacon: boolean): Promise<void> {
  if (!CONFIG.enabled || !CONFIG.toFile || BUFFER.length === 0) return;
  if (flushing) return;
  flushing = true;
  const batch = BUFFER.splice(0, BUFFER.length);
  await sendBatch(batch, useBeacon);
  flushing = false;
  if (BUFFER.length > 0) {
    scheduleFlush();
  }
}

function enqueue(entry: LogEntry): void {
  if (BUFFER.length >= MAX_BUFFER) {
    BUFFER.shift();
  }
  BUFFER.push(entry);
  if (BUFFER.length >= MAX_BUFFER) {
    void flush(false);
    return;
  }
  scheduleFlush();
}

function emit(level: LogLevel, message: string, meta?: LogMeta): void {
  if (!shouldLog(level, CONFIG)) return;

  const timestamp = new Date().toISOString();
  const resolvedMeta = typeof meta === "function" ? meta() : meta;
  const entry: LogEntry = { level, message, meta: resolvedMeta, timestamp };

  if (!CONFIG.toFile) {
    const method =
      level === "debug"
        ? console.debug
        : level === "info"
        ? console.info
        : level === "warn"
        ? console.warn
        : console.error;
    if (resolvedMeta !== undefined) {
      method(`[${timestamp}] ${message}`, resolvedMeta);
    } else {
      method(`[${timestamp}] ${message}`);
    }
  }

  if (CONFIG.toFile) {
    enqueue(entry);
  }
}

export const logger = {
  debug: (message: string, meta?: LogMeta) => emit("debug", message, meta),
  info: (message: string, meta?: LogMeta) => emit("info", message, meta),
  warn: (message: string, meta?: LogMeta) => emit("warn", message, meta),
  error: (message: string, meta?: LogMeta) => emit("error", message, meta),
};

if (HAS_WINDOW && CONFIG.enabled && CONFIG.toFile) {
  window.addEventListener("pagehide", () => {
    void flush(true);
  });
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        void flush(true);
      }
    });
  }
}
