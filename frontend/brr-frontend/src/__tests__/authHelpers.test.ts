/** Tests de helpers de auth (frontend). */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearStoredToken,
  getEmailFromToken,
  getStoredEmail,
  getStoredToken,
  isEmailAllowed,
  isTokenExpired,
  parseJwtPayload,
  readAllowedDomains,
  storeToken,
} from "@/lib/auth";

const originalEnv = { ...process.env };

const encode = (payload: object) => {
  const header = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString(
    "base64url"
  );
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.`;
};

describe("auth helpers", () => {
  afterEach(() => {
    process.env = { ...originalEnv };
    vi.restoreAllMocks();
  });

  it("parses jwt payload and email", () => {
    const token = encode({ email: "user@bbva.com" });
    expect(parseJwtPayload(token)?.email).toBe("user@bbva.com");
    expect(getEmailFromToken(token)).toBe("user@bbva.com");
  });

  it("returns null for invalid token", () => {
    expect(parseJwtPayload("bad")).toBeNull();
    expect(getEmailFromToken("bad")).toBeNull();
  });

  it("detects token expiry", () => {
    const expired = encode({ exp: Math.floor(Date.now() / 1000) - 60 });
    const fresh = encode({ exp: Math.floor(Date.now() / 1000) + 3600 });
    expect(isTokenExpired(expired)).toBe(true);
    expect(isTokenExpired(fresh)).toBe(false);
  });

  it("uses sessionStorage when available", () => {
    const session = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    Object.defineProperty(window, "sessionStorage", {
      value: session,
      configurable: true,
    });

    storeToken("tok", "user@bbva.com");
    expect(session.setItem).toHaveBeenCalled();
    expect(getStoredToken()).toBeNull();
    clearStoredToken();
    expect(session.removeItem).toHaveBeenCalled();
  });

  it("falls back to localStorage when sessionStorage is blocked", () => {
    const originalSession = window.sessionStorage;
    Object.defineProperty(window, "sessionStorage", {
      get() {
        throw new Error("blocked");
      },
      configurable: true,
    });
    const originalLocal = window.localStorage;
    const store: Record<string, string> = {};
    const local = {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => {
        store[key] = value;
      },
      removeItem: (key: string) => {
        delete store[key];
      },
    };
    Object.defineProperty(window, "localStorage", {
      value: local,
      configurable: true,
    });
    local.setItem("gor-google-id-token", "tok");
    local.setItem("gor-google-email", "user@bbva.com");
    expect(getStoredToken()).toBe("tok");
    expect(getStoredEmail()).toBe("user@bbva.com");
    Object.defineProperty(window, "localStorage", {
      value: originalLocal,
      configurable: true,
    });
    Object.defineProperty(window, "sessionStorage", {
      value: originalSession,
      configurable: true,
    });
  });

  it("returns null when storage access fails", () => {
    const originalSession = window.sessionStorage;
    const originalLocal = window.localStorage;
    Object.defineProperty(window, "sessionStorage", {
      value: undefined,
      configurable: true,
    });
    Object.defineProperty(window, "localStorage", {
      value: undefined,
      configurable: true,
    });
    expect(getStoredToken()).toBeNull();
    expect(getStoredEmail()).toBeNull();
    Object.defineProperty(window, "sessionStorage", {
      value: originalSession,
      configurable: true,
    });
    Object.defineProperty(window, "localStorage", {
      value: originalLocal,
      configurable: true,
    });
  });

  it("returns null for invalid json payload and uses Buffer fallback", () => {
    const originalAtob = window.atob;
    Object.defineProperty(window, "atob", {
      value: undefined,
      configurable: true,
    });
    const badPayload = Buffer.from("not-json").toString("base64url");
    const token = `x.${badPayload}.`;
    expect(parseJwtPayload(token)).toBeNull();
    Object.defineProperty(window, "atob", {
      value: originalAtob,
      configurable: true,
    });
  });

  it("validates allowed domains", () => {
    process.env.NEXT_PUBLIC_ALLOWED_DOMAINS = "bbva.com,example.com";
    expect(readAllowedDomains()).toEqual(["bbva.com", "example.com"]);
    expect(isEmailAllowed("user@bbva.com")).toBe(true);
    expect(isEmailAllowed("user@gmail.com")).toBe(false);
  });

  it("allows any email when no allowlists are configured", () => {
    process.env.NEXT_PUBLIC_ALLOWED_DOMAINS = "";
    process.env.NEXT_PUBLIC_ALLOWED_EMAILS = "";
    expect(isEmailAllowed("user@bbva.com")).toBe(true);
  });

  it("allows explicitly whitelisted emails", () => {
    process.env.NEXT_PUBLIC_ALLOWED_DOMAINS = "";
    process.env.NEXT_PUBLIC_ALLOWED_EMAILS = "user@bbva.com";
    expect(isEmailAllowed("user@bbva.com")).toBe(true);
    expect(isEmailAllowed("other@bbva.com")).toBe(false);
  });
});
