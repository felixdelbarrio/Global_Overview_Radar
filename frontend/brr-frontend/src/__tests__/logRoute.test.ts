/** Tests del endpoint /api/log. */

import { afterEach, describe, expect, it, vi } from "vitest";

const appendFileMock = vi.fn();
const mkdirMock = vi.fn();

vi.mock("node:fs/promises", () => ({
  __esModule: true,
  appendFile: appendFileMock,
  mkdir: mkdirMock,
  default: {
    appendFile: appendFileMock,
    mkdir: mkdirMock,
  },
}));

const originalEnv = { ...process.env };

const loadRoute = async (env: Record<string, string | undefined>) => {
  vi.resetModules();
  process.env = { ...originalEnv, ...env };
  return import("@/app/api/log/route");
};

afterEach(() => {
  process.env = { ...originalEnv };
  vi.clearAllMocks();
});

describe("POST /api/log", () => {
  it("returns 204 when logging disabled", async () => {
    const { POST } = await loadRoute({
      NEXT_PUBLIC_LOG_ENABLED: "false",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });
    const res = await POST(
      new Request("http://localhost/api/log", {
        method: "POST",
        body: JSON.stringify({ message: "hola" }),
      })
    );
    expect(res.status).toBe(204);
  });

  it("rejects invalid payload", async () => {
    const { POST } = await loadRoute({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });
    const res = await POST(
      new Request("http://localhost/api/log", {
        method: "POST",
        body: "not-json",
      })
    );
    expect(res.status).toBe(400);
  });

  it("writes logs when enabled", async () => {
    const { POST } = await loadRoute({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
      NEXT_PUBLIC_LOG_DEBUG: "false",
      LOG_FILE_NAME: "frontend.log",
    });
    const res = await POST(
      new Request("http://localhost/api/log", {
        method: "POST",
        body: JSON.stringify({
          entries: [
            {
              level: "info",
              message: "hola",
              timestamp: "2025-01-01T00:00:00Z",
            },
          ],
        }),
      })
    );
    expect(res.status).toBe(204);
    expect(mkdirMock).toHaveBeenCalled();
    expect(appendFileMock).toHaveBeenCalled();
  });

  it("accepts single object payloads", async () => {
    const { POST } = await loadRoute({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });
    const res = await POST(
      new Request("http://localhost/api/log", {
        method: "POST",
        body: JSON.stringify({ level: "warn", message: "hola" }),
      })
    );
    expect(res.status).toBe(204);
    expect(appendFileMock).toHaveBeenCalled();
  });

  it("skips debug entries when debug logging is disabled", async () => {
    const { POST } = await loadRoute({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
      NEXT_PUBLIC_LOG_DEBUG: "false",
    });
    const res = await POST(
      new Request("http://localhost/api/log", {
        method: "POST",
        body: JSON.stringify([{ level: "debug", message: "detalle" }]),
      })
    );
    expect(res.status).toBe(204);
    expect(appendFileMock).not.toHaveBeenCalled();
  });

  it("rejects payloads with invalid entries shape", async () => {
    const { POST } = await loadRoute({
      NEXT_PUBLIC_LOG_ENABLED: "true",
      NEXT_PUBLIC_LOG_TO_FILE: "true",
    });
    const res = await POST(
      new Request("http://localhost/api/log", {
        method: "POST",
        body: JSON.stringify({ entries: "oops" }),
      })
    );
    expect(res.status).toBe(400);
  });
});
