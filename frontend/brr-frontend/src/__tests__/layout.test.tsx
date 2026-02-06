/** Tests del layout raiz. */

import React from "react";
import { render, screen } from "@testing-library/react";
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
  render(
    <RootLayout>
      <div>Hola</div>
    </RootLayout>
  );
  expect(screen.getByText("Hola")).toBeInTheDocument();
});
