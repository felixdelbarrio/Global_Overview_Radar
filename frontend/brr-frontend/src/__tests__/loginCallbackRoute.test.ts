/** Tests del endpoint /login/callback (redirect login). */

import { describe, expect, it, vi } from "vitest";

type CookieValue = { value: string } | undefined;

const cookieStore = {
  get: vi.fn<string, [string]>(),
};

vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve(cookieStore),
}));

const loadRoute = async () => {
  vi.resetModules();
  return import("@/app/login/callback/route");
};

const setCookies = (values: Record<string, string | undefined>) => {
  cookieStore.get.mockImplementation((key: string): CookieValue => {
    const value = values[key];
    return value ? { value } : undefined;
  });
};

describe("POST /login/callback", () => {
  it("rejects requests without credential", async () => {
    setCookies({});
    const { POST } = await loadRoute();
    const form = new FormData();
    const res = await POST(
      new Request("http://localhost/login/callback", {
        method: "POST",
        body: form,
      })
    );
    expect(res.status).toBe(400);
  });

  it("rejects when CSRF token mismatches", async () => {
    setCookies({ g_csrf_token: "cookie-token" });
    const { POST } = await loadRoute();
    const form = new FormData();
    form.set("credential", "token");
    form.set("g_csrf_token", "form-token");
    const res = await POST(
      new Request("http://localhost/login/callback", {
        method: "POST",
        body: form,
      })
    );
    expect(res.status).toBe(400);
  });

  it("stores token and redirects to next path", async () => {
    setCookies({ g_csrf_token: "same-token", "gor-login-next": "/sentimiento" });
    const { POST } = await loadRoute();
    const form = new FormData();
    form.set("credential", "token");
    form.set("g_csrf_token", "same-token");
    const res = await POST(
      new Request("http://localhost/login/callback", {
        method: "POST",
        body: form,
      })
    );
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).toContain('var nextPath = "/sentimiento";');
  });

  it("falls back to root when next path is unsafe", async () => {
    setCookies({ g_csrf_token: "ok", "gor-login-next": "https://evil.com" });
    const { POST } = await loadRoute();
    const form = new FormData();
    form.set("credential", "token");
    form.set("g_csrf_token", "ok");
    const res = await POST(
      new Request("http://localhost/login/callback", {
        method: "POST",
        body: form,
      })
    );
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).toContain('var nextPath = "/";');
  });
});
