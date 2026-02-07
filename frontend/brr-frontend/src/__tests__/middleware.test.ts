/** Tests del middleware. */

import { afterEach, describe, expect, it, vi } from "vitest";

const nextSpy = vi.fn(() => new Response("ok"));

vi.mock("next/server", () => ({
  NextResponse: {
    next: nextSpy,
  },
}));

const originalEnv = { ...process.env };

const loadMiddleware = async (enabled: boolean) => {
  vi.resetModules();
  process.env = { ...originalEnv, NEXT_PUBLIC_AUTH_ENABLED: enabled ? "true" : "false" };
  return import("@/middleware");
};

afterEach(() => {
  process.env = { ...originalEnv };
  vi.clearAllMocks();
});

describe("middleware", () => {
  it("returns next without logging when disabled", async () => {
    const { middleware } = await loadMiddleware(false);
    const req = {
      headers: new Headers(),
      nextUrl: { pathname: "/" },
      method: "GET",
    };
    const res = middleware(req as any);
    expect(res).toBeInstanceOf(Response);
    expect(nextSpy).toHaveBeenCalled();
  });

  it("logs access details when enabled", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const { middleware } = await loadMiddleware(true);
    const req = {
      headers: new Headers({
        "x-goog-authenticated-user-email": "accounts.google.com:felix@bbva.com",
        "x-goog-authenticated-user-id": "accounts.google.com:123",
        "x-forwarded-for": "1.2.3.4, 5.6.7.8",
        "user-agent": "jest",
      }),
      nextUrl: { pathname: "/home" },
      method: "GET",
      ip: "9.9.9.9",
    };
    middleware(req as any);
    expect(logSpy).toHaveBeenCalled();
  });

  it("handles missing headers and ips gracefully", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const { middleware } = await loadMiddleware(true);
    const req = {
      headers: new Headers(),
      nextUrl: { pathname: "/empty" },
      method: "POST",
    };
    middleware(req as any);
    expect(logSpy).toHaveBeenCalled();
  });
});
