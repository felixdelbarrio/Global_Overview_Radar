/** Tests del proxy /api/[...path] */

import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const originalEnv = { ...process.env };

const loadRoute = async (env: Record<string, string | undefined>) => {
  vi.resetModules();
  process.env = { ...originalEnv, ...env };
  return import("@/app/api/[...path]/route");
};

afterEach(() => {
  process.env = { ...originalEnv };
  vi.restoreAllMocks();
});

describe("proxy route", () => {
  it("blocks mutating requests in auth-bypass read-only mode", async () => {
    const fetchMock = vi.fn();
    global.fetch = fetchMock as typeof fetch;

    const { POST } = await loadRoute({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "false",
      AUTH_BYPASS_READ_ONLY: "true",
      USE_SERVER_PROXY: "true",
      API_PROXY_TARGET: "https://api.example.com",
    });

    const req = new Request("http://localhost/api/ingest/reputation", {
      method: "POST",
      body: JSON.stringify({ force: false }),
    });
    const res = await POST(req as unknown as NextRequest, {
      params: Promise.resolve({ path: ["ingest", "reputation"] }),
    });

    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("allows mutating requests in auth-bypass mode when read-only override is disabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("ok", {
        status: 200,
      })
    );
    global.fetch = fetchMock as typeof fetch;

    const { POST } = await loadRoute({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "false",
      AUTH_BYPASS_READ_ONLY: "false",
      USE_SERVER_PROXY: "false",
      API_PROXY_TARGET: "https://api.example.com",
    });

    const req = new Request("http://localhost/api/items", {
      method: "POST",
      body: "payload",
    });
    const res = await POST(req as unknown as NextRequest, {
      params: Promise.resolve({ path: ["items"] }),
    });

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("proxies requests without id token when disabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("ok", {
        status: 200,
        headers: { "x-upstream": "1" },
      })
    );
    global.fetch = fetchMock as typeof fetch;

    const { GET } = await loadRoute({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      USE_SERVER_PROXY: "false",
      API_PROXY_TARGET: "https://api.example.com/",
    });

    const req = new Request("http://localhost/api/kpis?x=1", {
      headers: {
        connection: "keep-alive",
        "x-gor-admin-key": "attempted-forward",
      },
    });
    const res = await GET(req as unknown as NextRequest, {
      params: Promise.resolve({ path: ["kpis"] }),
    });

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.com/kpis?x=1");
    expect((options as RequestInit).redirect).toBe("manual");
    const headers = (options as RequestInit).headers as Headers;
    expect(headers.get("connection")).toBeNull();
    expect(headers.get("x-gor-admin-key")).toBeNull();
  });

  it("allows mutating requests in auth-bypass read-only mode when admin key is provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("ok", {
        status: 200,
      })
    );
    global.fetch = fetchMock as typeof fetch;

    const { POST } = await loadRoute({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "false",
      AUTH_BYPASS_READ_ONLY: "true",
      USE_SERVER_PROXY: "false",
      API_PROXY_TARGET: "https://api.example.com",
    });

    const req = new Request("http://localhost/api/ingest/reputation", {
      method: "POST",
      body: JSON.stringify({ force: false }),
      headers: {
        "x-gor-admin-key": "admin-key",
      },
    });
    const res = await POST(req as unknown as NextRequest, {
      params: Promise.resolve({ path: ["ingest", "reputation"] }),
    });

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("adds id token when server proxy is enabled", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response("token", {
          status: 200,
        })
      )
      .mockResolvedValueOnce(
        new Response("ok", {
          status: 200,
        })
      );
    global.fetch = fetchMock as typeof fetch;

    const { GET } = await loadRoute({
      USE_SERVER_PROXY: "true",
      API_PROXY_TARGET: "https://api.example.com",
    });

    const req = new Request("http://localhost/api/log", { method: "GET" });
    await GET(req as unknown as NextRequest, {
      params: Promise.resolve({ path: ["log"] }),
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [, options] = fetchMock.mock.calls[1];
    const headers = (options as RequestInit).headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer token");
    expect(headers.get("x-gor-proxy-auth")).toBe("cloudrun-idtoken");
  });

  it("uses render fallback when proxy target is not set", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("ok", {
        status: 200,
      })
    );
    global.fetch = fetchMock as typeof fetch;

    const { GET } = await loadRoute({
      USE_SERVER_PROXY: "false",
      VERCEL: "1",
    });

    const req = new Request("http://localhost/api?x=1", { method: "GET" });
    await GET(req as unknown as NextRequest, {
      params: Promise.resolve({} as { path?: string[] }),
    });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("https://global-overview-radar.onrender.com?x=1");
  });

  it("forwards request bodies for non-GET methods", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("ok", {
        status: 200,
      })
    );
    global.fetch = fetchMock as typeof fetch;

    const { POST } = await loadRoute({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      USE_SERVER_PROXY: "false",
      API_PROXY_TARGET: "https://api.example.com",
    });

    const req = new Request("http://localhost/api/items", {
      method: "POST",
      body: "payload",
    });
    await POST(req as unknown as NextRequest, {
      params: Promise.resolve({ path: ["items"] }),
    });

    const [, options] = fetchMock.mock.calls[0];
    expect((options as RequestInit).body).toBeInstanceOf(ArrayBuffer);
  });

  it("throws when metadata token fetch fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("fail", {
        status: 500,
      })
    );
    global.fetch = fetchMock as typeof fetch;

    const { GET } = await loadRoute({
      USE_SERVER_PROXY: "true",
      API_PROXY_TARGET: "https://api.example.com",
    });

    const req = new Request("http://localhost/api/log", { method: "GET" });
    await expect(
      GET(req as unknown as NextRequest, {
        params: Promise.resolve({ path: ["log"] }),
      })
    ).rejects.toThrow("metadata identity token failed");
  });
});
