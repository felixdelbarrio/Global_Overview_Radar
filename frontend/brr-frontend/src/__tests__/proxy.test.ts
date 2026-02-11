/** Tests del proxy (sustituye middleware). */

import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const nextSpy = vi.fn(() => new Response("ok"));

vi.mock("next/server", () => ({
  NextResponse: {
    next: nextSpy,
  },
}));

const originalEnv = { ...process.env };

const loadProxy = async (loginRequired: boolean) => {
  vi.resetModules();
  process.env = {
    ...originalEnv,
    NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: loginRequired ? "true" : "false",
  };
  return import("@/proxy");
};

afterEach(() => {
  process.env = { ...originalEnv };
  vi.clearAllMocks();
});

describe("proxy", () => {
  it("returns next without logging when disabled", async () => {
    const { proxy } = await loadProxy(false);
    const req = {
      headers: new Headers(),
      nextUrl: { pathname: "/" },
      method: "GET",
    };
    const res = proxy(req as unknown as NextRequest);
    expect(res).toBeInstanceOf(Response);
    expect(nextSpy).toHaveBeenCalled();
  });

  it("logs access details when enabled", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const { proxy } = await loadProxy(true);
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
    proxy(req as unknown as NextRequest);
    expect(logSpy).toHaveBeenCalled();
  });

  it("handles missing headers and ips gracefully", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const { proxy } = await loadProxy(true);
    const req = {
      headers: new Headers(),
      nextUrl: { pathname: "/empty" },
      method: "POST",
    };
    proxy(req as unknown as NextRequest);
    expect(logSpy).toHaveBeenCalled();
  });

  it("skips logging when bypass is enabled", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const { proxy } = await loadProxy(false);
    const req = {
      headers: new Headers(),
      nextUrl: { pathname: "/bypass" },
      method: "GET",
    };
    proxy(req as unknown as NextRequest);
    expect(logSpy).not.toHaveBeenCalled();
  });
});
