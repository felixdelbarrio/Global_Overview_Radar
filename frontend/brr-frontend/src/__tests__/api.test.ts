/** Tests del helper apiGet del frontend. */

import { expect, it, vi } from "vitest";
import { apiGet } from "@/lib/api";

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
