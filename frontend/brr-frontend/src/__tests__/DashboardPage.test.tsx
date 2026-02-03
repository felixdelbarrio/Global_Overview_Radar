/** Tests del dashboard reputacional. */

import React from "react";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
}));

import { apiGet } from "@/lib/api";
import DashboardPage from "@/app/page";

const apiGetMock = vi.mocked(apiGet);

it("renders dashboard header and combined mentions", async () => {
  apiGetMock.mockImplementation((path: string) => {
    if (path.startsWith("/reputation/meta")) {
      return Promise.resolve({
        actor_principal: { canonical: "BBVA" },
        geos: ["España"],
        sources_enabled: ["gdelt"],
        sources_available: ["gdelt"],
        incidents_available: true,
        ui: { incidents_enabled: true, ops_enabled: true },
      });
    }
    if (path.startsWith("/reputation/items")) {
      return Promise.resolve({
        generated_at: "2025-01-02T00:00:00Z",
        config_hash: "hash",
        sources_enabled: ["gdelt"],
        items: [
          {
            id: "1",
            source: "gdelt",
            geo: "España",
            actor: "BBVA",
            title: "Comentario positivo",
            text: "Excelente servicio",
            sentiment: "positive",
            published_at: "2025-01-01T10:00:00Z",
            signals: { sentiment_score: 0.5 },
          },
        ],
        stats: { count: 1 },
      });
    }
    if (path.startsWith("/incidents")) {
      return Promise.resolve({
        items: [
          {
            global_id: "INC-1",
            title: "Caída app",
            status: "OPEN",
            severity: "HIGH",
            opened_at: "2025-01-01",
            updated_at: "2025-01-02",
            product: "App",
            feature: "Login",
          },
        ],
      });
    }
    if (path.startsWith("/evolution")) {
      return Promise.resolve({
        days: 10,
        series: [{ date: "2025-01-01", open: 1, new: 1, closed: 0 }],
      });
    }
    return Promise.resolve({});
  });

  render(<DashboardPage />);

  expect(await screen.findByText("Dashboard reputacional")).toBeInTheDocument();
  expect(await screen.findByText("Caída app")).toBeInTheDocument();
});
