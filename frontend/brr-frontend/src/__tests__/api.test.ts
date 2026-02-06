/** Tests del helper apiGet/apiPost del frontend. */

import { expect, it, vi } from "vitest";

vi.mock("@/lib/logger", () => ({
  logger: {
    debug: vi.fn(),
    warn: vi.fn(),
  },
}));

import { apiGet } from "@/lib/api";
import { apiPost } from "@/lib/api";

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
