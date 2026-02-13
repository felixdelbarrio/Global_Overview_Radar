/** Tests del helper apiGet/apiPost del frontend. */

import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("@/lib/logger", () => ({
  logger: {
    debug: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  },
}));

import { apiGet, apiGetCached, apiPost, clearApiCache } from "@/lib/api";

const originalEnv = { ...process.env };

async function loadApiModuleWithAuth({
  loginRequired,
  storedToken,
  tokenExpired,
}: {
  loginRequired: boolean;
  storedToken: string | null;
  tokenExpired: boolean;
}) {
  vi.resetModules();
  process.env = {
    ...originalEnv,
    NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: loginRequired ? "true" : "false",
  };

  const authMocks = {
    clearStoredToken: vi.fn(),
    getStoredToken: vi.fn(() => storedToken),
    isTokenExpired: vi.fn(() => tokenExpired),
  };

  vi.doMock("@/lib/auth", () => authMocks);

  const mod = await import("@/lib/api");
  return { ...mod, authMocks };
}

beforeEach(() => {
  clearApiCache();
});

afterEach(() => {
  process.env = { ...originalEnv };
  vi.restoreAllMocks();
});

it("apiGet returns json on success", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
  });
  global.fetch = fetchMock as typeof fetch;

  const res = await apiGet<{ ok: boolean }>("/kpis");
  expect(res.ok).toBe(true);
});

it("apiGet throws on error", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: false,
    status: 500,
    text: async () => "boom",
  });
  global.fetch = fetchMock as typeof fetch;

  await expect(apiGet("/kpis")).rejects.toThrow("API /kpis failed: 500");
});

it("apiPost returns json on success", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
  });
  global.fetch = fetchMock as typeof fetch;

  const res = await apiPost<{ ok: boolean }>("/ingest", { force: true });
  expect(res.ok).toBe(true);
});

it("apiPost throws on error", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: false,
    status: 400,
    text: async () => "bad",
  });
  global.fetch = fetchMock as typeof fetch;

  await expect(apiPost("/ingest", { force: true })).rejects.toThrow(
    "API /ingest failed: 400 — bad"
  );
});

it("apiGet builds URL without leading slash and omits empty text", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: false,
    status: 500,
    text: async () => "",
  });
  global.fetch = fetchMock as typeof fetch;

  await expect(apiGet("kpis")).rejects.toThrow("API kpis failed: 500");
  expect(fetchMock).toHaveBeenCalledWith("/api/kpis", { cache: "no-store" });
});

it("apiPost builds URL without leading slash", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
  });
  global.fetch = fetchMock as typeof fetch;

  await apiPost("ingest", { force: true });
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/ingest",
    expect.objectContaining({ method: "POST" })
  );
});

it("apiGetCached reuses cached value while TTL is valid", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
  });
  global.fetch = fetchMock as typeof fetch;

  const first = await apiGetCached<{ ok: boolean }>("/kpis", { ttlMs: 60000 });
  const second = await apiGetCached<{ ok: boolean }>("/kpis", { ttlMs: 60000 });

  expect(first.ok).toBe(true);
  expect(second.ok).toBe(true);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("apiGetCached shares in-flight promise for same key", async () => {
  let resolveFetch: ((value: { ok: boolean; json: () => Promise<{ ok: boolean }> }) => void) | null =
    null;
  const fetchMock = vi.fn().mockReturnValue(
    new Promise((resolve) => {
      resolveFetch = resolve;
    })
  );
  global.fetch = fetchMock as typeof fetch;

  const firstPromise = apiGetCached<{ ok: boolean }>("/kpis", { ttlMs: 60000 });
  const secondPromise = apiGetCached<{ ok: boolean }>("/kpis", { ttlMs: 60000 });

  expect(fetchMock).toHaveBeenCalledTimes(1);
  resolveFetch?.({
    ok: true,
    json: async () => ({ ok: true }),
  });
  const [first, second] = await Promise.all([firstPromise, secondPromise]);
  expect(first.ok).toBe(true);
  expect(second.ok).toBe(true);
});

it("apiGetCached force=true bypasses cache", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ n: 1 }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ n: 2 }),
    });
  global.fetch = fetchMock as typeof fetch;

  const first = await apiGetCached<{ n: number }>("/kpis", { ttlMs: 60000 });
  const second = await apiGetCached<{ n: number }>("/kpis", {
    ttlMs: 60000,
    force: true,
  });

  expect(first.n).toBe(1);
  expect(second.n).toBe(2);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("apiGetCached clears broken cache entry when request fails", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: async () => "boom",
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ok: true }),
    });
  global.fetch = fetchMock as typeof fetch;

  await expect(apiGetCached("/kpis", { ttlMs: 60000 })).rejects.toThrow(
    "API /kpis failed: 500 — boom"
  );
  const recovered = await apiGetCached<{ ok: boolean }>("/kpis", { ttlMs: 60000 });
  expect(recovered.ok).toBe(true);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("apiGet attaches user token header when login is required", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
  });
  global.fetch = fetchMock as typeof fetch;

  const { apiGet, authMocks } = await loadApiModuleWithAuth({
    loginRequired: true,
    storedToken: "id-token",
    tokenExpired: false,
  });

  const response = await apiGet<{ ok: boolean }>("/kpis");
  expect(response.ok).toBe(true);
  expect(fetchMock).toHaveBeenCalledWith("/api/kpis", {
    cache: "no-store",
    headers: { "x-user-id-token": "id-token" },
  });
  expect(authMocks.getStoredToken).toHaveBeenCalled();
  expect(authMocks.isTokenExpired).toHaveBeenCalledWith("id-token");
  expect(authMocks.clearStoredToken).not.toHaveBeenCalled();
});

it("apiGet clears expired user token before sending request", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
  });
  global.fetch = fetchMock as typeof fetch;

  const { apiGet, authMocks } = await loadApiModuleWithAuth({
    loginRequired: true,
    storedToken: "expired-token",
    tokenExpired: true,
  });

  await apiGet<{ ok: boolean }>("/kpis");
  expect(authMocks.clearStoredToken).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith("/api/kpis", {
    cache: "no-store",
    headers: undefined,
  });
});

it("apiGet clears stored token on unauthorized response when login is required", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: false,
    status: 401,
    text: async () => "",
  });
  global.fetch = fetchMock as typeof fetch;

  const { apiGet, authMocks } = await loadApiModuleWithAuth({
    loginRequired: true,
    storedToken: "valid-token",
    tokenExpired: false,
  });

  await expect(apiGet("/kpis")).rejects.toThrow("API /kpis failed: 401");
  expect(authMocks.clearStoredToken).toHaveBeenCalledTimes(1);
});

it("apiPost clears stored token on unauthorized response when login is required", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: false,
    status: 401,
    text: async () => "",
  });
  global.fetch = fetchMock as typeof fetch;

  const { apiPost, authMocks } = await loadApiModuleWithAuth({
    loginRequired: true,
    storedToken: "valid-token",
    tokenExpired: false,
  });

  await expect(apiPost("/ingest", { force: true })).rejects.toThrow("API /ingest failed: 401");
  expect(authMocks.clearStoredToken).toHaveBeenCalledTimes(1);
});
