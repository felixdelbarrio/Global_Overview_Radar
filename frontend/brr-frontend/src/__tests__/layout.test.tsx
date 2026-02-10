/** Tests del layout raiz. */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("next/font/google", () => ({
  Space_Grotesk: () => ({ variable: "--font-display" }),
  Source_Sans_3: () => ({ variable: "--font-body" }),
}));

vi.mock("next/script", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <script>{children}</script>
  ),
}));

vi.mock("@/components/AuthGate", () => ({
  AuthGate: ({ children }: { children: React.ReactNode }) => (
    <div data-auth-gate>{children}</div>
  ),
}));

const originalEnv = { ...process.env };

const loadLayout = async (authEnabled: boolean, bypass = false) => {
  vi.resetModules();
  process.env = {
    ...originalEnv,
    NEXT_PUBLIC_AUTH_ENABLED: authEnabled ? "true" : "false",
    NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: bypass ? "true" : "false",
  };
  return (await import("@/app/layout")).default;
};

afterEach(() => {
  process.env = { ...originalEnv };
});

it("renders root layout with children when auth disabled", async () => {
  const RootLayout = await loadLayout(false);
  const html = renderToStaticMarkup(
    <RootLayout>
      <div>Hola</div>
    </RootLayout>
  );
  expect(html).toContain("Hola");
  expect(html).not.toContain("data-auth-gate");
});

it("wraps children with AuthGate when auth enabled", async () => {
  const RootLayout = await loadLayout(true);
  const html = renderToStaticMarkup(
    <RootLayout>
      <div>Hola</div>
    </RootLayout>
  );
  expect(html).toContain("data-auth-gate");
});

it("does not wrap children when login bypass is enabled", async () => {
  const RootLayout = await loadLayout(true, true);
  const html = renderToStaticMarkup(
    <RootLayout>
      <div>Hola</div>
    </RootLayout>
  );
  expect(html).toContain("Hola");
  expect(html).not.toContain("data-auth-gate");
});
