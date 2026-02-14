/** Tests de wrappers de rutas de sentimiento. */

import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/dynamic", () => ({
  default: () =>
    ({ mode, scope }: { mode: string; scope: string }) => (
      <div data-testid="sentiment-view-proxy" data-mode={mode} data-scope={scope} />
    ),
}));

import LoginPage from "@/app/login/page";
import SentimientoMarketsPage from "@/app/sentimiento/markets/page";
import SentimientoPrensaPage from "@/app/sentimiento/prensa/page";

describe("Sentiment route wrappers", () => {
  it("renders empty login page client placeholder", () => {
    const { container } = render(<LoginPage />);
    expect(container.firstChild).toBeNull();
  });

  it("renders markets wrapper with sentiment scope", () => {
    render(<SentimientoMarketsPage />);
    const proxy = screen.getByTestId("sentiment-view-proxy");
    expect(proxy).toHaveAttribute("data-mode", "sentiment");
    expect(proxy).toHaveAttribute("data-scope", "markets");
  });

  it("renders press wrapper with sentiment scope", () => {
    render(<SentimientoPrensaPage />);
    const proxy = screen.getByTestId("sentiment-view-proxy");
    expect(proxy).toHaveAttribute("data-mode", "sentiment");
    expect(proxy).toHaveAttribute("data-scope", "press");
  });
});
