/** Tests del layout raiz. */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("next/font/google", () => ({
  Space_Grotesk: () => ({ variable: "--font-display" }),
  Source_Sans_3: () => ({ variable: "--font-body" }),
}));

vi.mock("next/script", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <script>{children}</script>
  ),
}));

import RootLayout from "@/app/layout";

it("renders root layout with children", () => {
  const html = renderToStaticMarkup(
    <RootLayout>
      <div>Hola</div>
    </RootLayout>
  );
  expect(html).toContain("Hola");
});
