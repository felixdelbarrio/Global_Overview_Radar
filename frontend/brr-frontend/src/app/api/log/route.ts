import { appendFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export const runtime = "nodejs";

function parseBool(value: string | undefined): boolean {
  return (value ?? "").trim().toLowerCase() === "true";
}

const LOG_ENABLED = parseBool(process.env.NEXT_PUBLIC_LOG_ENABLED);
const LOG_TO_FILE = parseBool(process.env.NEXT_PUBLIC_LOG_TO_FILE);
const LOG_DEBUG = parseBool(process.env.NEXT_PUBLIC_LOG_DEBUG);
const LOG_FILE_NAME = process.env.LOG_FILE_NAME || "frontend.log";

type LogPayload = {
  level?: "debug" | "info" | "warn" | "error";
  message?: string;
  meta?: unknown;
  timestamp?: string;
};

type LogBatch = LogPayload | LogPayload[] | { entries?: LogPayload[] };

function normalizePayload(payload: LogBatch): LogPayload[] {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === "object" && "entries" in payload) {
    const entries = (payload as { entries?: LogPayload[] }).entries;
    return Array.isArray(entries) ? entries : [];
  }
  if (payload && typeof payload === "object") return [payload as LogPayload];
  return [];
}

export async function POST(request: Request): Promise<Response> {
  if (!LOG_ENABLED || !LOG_TO_FILE) {
    return new Response(null, { status: 204 });
  }

  let payload: LogBatch | null = null;
  try {
    payload = (await request.json()) as LogBatch;
  } catch {
    return new Response("invalid payload", { status: 400 });
  }

  const entries = normalizePayload(payload ?? {});
  if (entries.length === 0) {
    return new Response("invalid payload", { status: 400 });
  }

  const lines: string[] = [];
  for (const entry of entries) {
    if (!entry?.message) continue;
    if (entry.level === "debug" && !LOG_DEBUG) continue;
    lines.push(
      JSON.stringify({
        timestamp: entry.timestamp ?? new Date().toISOString(),
        level: entry.level ?? "info",
        message: entry.message,
        meta: entry.meta ?? null,
      }),
    );
  }
  if (lines.length === 0) {
    return new Response(null, { status: 204 });
  }

  const resolvedPath = resolve(process.cwd(), "logs", LOG_FILE_NAME);
  await mkdir(dirname(resolvedPath), { recursive: true });
  await appendFile(resolvedPath, `${lines.join("\n")}\n`, "utf-8");

  return new Response(null, { status: 204 });
}
