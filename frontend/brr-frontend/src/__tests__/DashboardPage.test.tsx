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
  apiGetCached: vi.fn(),
}));

import { apiGet, apiGetCached } from "@/lib/api";
import DashboardPage from "@/app/page";

const apiGetMock = vi.mocked(apiGet);
const apiGetCachedMock = vi.mocked(apiGetCached);

it("renders dashboard header and combined mentions", async () => {
  const handleGet = (path: string) => {
    if (path.startsWith("/reputation/meta")) {
      return Promise.resolve({
        actor_principal: { canonical: "BBVA" },
        geos: ["España"],
        sources_enabled: ["gdelt", "appstore"],
        sources_available: ["gdelt", "appstore"],
        market_ratings: [
          {
            source: "appstore",
            actor: "BBVA",
            geo: "España",
            rating: 4.1,
            rating_count: 80,
            collected_at: "2025-01-01T00:00:00Z",
          },
        ],
      });
    }
    if (path.startsWith("/reputation/items")) {
      return Promise.resolve({
        generated_at: "2025-01-02T00:00:00Z",
        config_hash: "hash",
        sources_enabled: ["gdelt", "appstore"],
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
          {
            id: "2",
            source: "appstore",
            geo: "España",
            actor: "BBVA",
            title: "Reseña App",
            text: "Muy útil",
            sentiment: "positive",
            published_at: "2025-01-02T10:00:00Z",
            signals: { sentiment_score: 0.7, rating: 4.2 },
          },
        ],
        stats: { count: 2 },
      });
    }
    if (path.startsWith("/reputation/responses/summary")) {
      return Promise.resolve({
        totals: {
          opinions_total: 2,
          answered_total: 1,
          answered_ratio: 0.5,
          answered_positive: 1,
          answered_neutral: 0,
          answered_negative: 0,
          unanswered_positive: 1,
          unanswered_neutral: 0,
          unanswered_negative: 0,
        },
        actor_breakdown: [],
        repeated_replies: [],
        answered_items: [],
      });
    }
    return Promise.resolve({});
  };
  apiGetMock.mockImplementation(handleGet);
  apiGetCachedMock.mockImplementation(handleGet);

  render(<DashboardPage />);

  expect(await screen.findByText("Dashboard reputacional")).toBeInTheDocument();
  expect(await screen.findByText("Comentario positivo")).toBeInTheDocument();
});

it("renders latest mentions without waiting for chart dataset", async () => {
  const pendingChartRequest = new Promise<never>(() => {
    // intentionally unresolved: emulates slow chart query on first load
  });

  const handleCachedGet = (path: string) => {
    if (path.startsWith("/reputation/meta")) {
      return Promise.resolve({
        actor_principal: { canonical: "BBVA" },
        geos: ["España"],
        sources_enabled: ["gdelt", "appstore"],
        sources_available: ["gdelt", "appstore"],
      });
    }
    if (path.startsWith("/reputation/profiles")) {
      return Promise.resolve({
        active: { source: "samples", profiles: [], profile_key: "default" },
        options: { default: [], samples: [] },
      });
    }
    return Promise.resolve({});
  };

  const handleGet = (path: string) => {
    if (path.startsWith("/reputation/items")) {
      if (!path.includes("entity=actor_principal")) {
        return pendingChartRequest;
      }
      return Promise.resolve({
        generated_at: "2025-01-02T00:00:00Z",
        config_hash: "hash",
        sources_enabled: ["gdelt", "appstore"],
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
    if (path.startsWith("/reputation/responses/summary")) {
      return Promise.resolve({
        totals: {
          opinions_total: 1,
          answered_total: 0,
          answered_ratio: 0,
          answered_positive: 0,
          answered_neutral: 0,
          answered_negative: 0,
          unanswered_positive: 1,
          unanswered_neutral: 0,
          unanswered_negative: 0,
        },
        actor_breakdown: [],
        repeated_replies: [],
        answered_items: [],
      });
    }
    return Promise.resolve({});
  };

  apiGetCachedMock.mockImplementation(handleCachedGet);
  apiGetMock.mockImplementation(handleGet);

  render(<DashboardPage />);

  expect(await screen.findByText("Comentario positivo")).toBeInTheDocument();
});
