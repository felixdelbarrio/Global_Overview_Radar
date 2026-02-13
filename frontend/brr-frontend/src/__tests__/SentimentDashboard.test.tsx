/** Tests del modo dashboard de SentimentView. */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiGetCached: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiGetCached, apiPost } from "@/lib/api";
import { SentimentView } from "@/components/SentimentView";

const apiGetMock = vi.mocked(apiGet);
const apiGetCachedMock = vi.mocked(apiGetCached);
const apiPostMock = vi.mocked(apiPost);

const metaResponse = {
  actor_principal: { canonical: "Acme Bank", aliases: ["Acme"] },
  geos: ["España"],
  otros_actores_por_geografia: {},
  otros_actores_globales: [],
  sources_enabled: ["news"],
  sources_available: ["news"],
  cache_available: true,
  market_ratings: [],
  market_ratings_history: [],
};

const itemsResponse = {
  generated_at: "2025-01-12T00:00:00Z",
  config_hash: "hash",
  sources_enabled: ["news"],
  items: [
    {
      id: "p1",
      source: "news",
      geo: "España",
      actor: "Acme Bank",
      title: "Acme Bank mejora",
      text: "Servicio excelente",
      sentiment: "positive",
      published_at: "2025-01-01T10:00:00Z",
      signals: { sentiment_score: 0.6 },
    },
  ],
  stats: { count: 1 },
};

const profilesResponse = {
  active: { source: "default", profiles: ["banking"], profile_key: "banking" },
  options: { default: ["banking"], samples: [] },
};

describe("SentimentView dashboard", () => {
  beforeEach(() => {
    const handleGet = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(metaResponse);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(itemsResponse);
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
      if (path.startsWith("/reputation/markets/insights")) {
        return Promise.resolve({
          generated_at: "2025-01-12T00:00:00Z",
          principal_actor: "Acme Bank",
          comparisons_enabled: false,
          filters: { geo: "España", from_date: "2025-01-01", to_date: "2025-01-31", sources: [] },
          kpis: {
            total_mentions: 1,
            negative_mentions: 0,
            negative_ratio: 0,
            positive_mentions: 1,
            neutral_mentions: 0,
            unique_authors: 1,
            recurring_authors: 0,
            average_sentiment_score: 0.6,
          },
          daily_volume: [{ date: "2025-01-01", count: 1 }],
          geo_summary: [],
          recurring_authors: [],
          top_penalized_features: [{ feature: "login", key: "login", count: 1, evidence: [] }],
          source_friction: [
            {
              source: "news",
              total: 1,
              negative: 0,
              positive: 1,
              neutral: 0,
              negative_ratio: 0,
              top_features: [{ feature: "login", count: 1 }],
            },
          ],
          alerts: [
            {
              id: "alert-1",
              severity: "low",
              title: "Seguimiento",
              summary: "Mantener vigilancia.",
            },
          ],
          responses: undefined,
          newsletter_by_geo: [],
        });
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({});
    };
    apiGetMock.mockImplementation(handleGet);
    apiGetCachedMock.mockImplementation(handleGet);
    apiPostMock.mockResolvedValue({});
  });

  it("renders dashboard header", async () => {
    render(<SentimentView mode="dashboard" />);
    expect(await screen.findByText("Dashboard reputacional")).toBeInTheDocument();
    expect(await screen.findByText("TOP 10 FUNCIONALIDADES PENALIZADAS")).toBeInTheDocument();
    expect(await screen.findByText("ALERTAS CALIENTES")).toBeInTheDocument();
    expect(await screen.findByText("MAPA DE CALOR DE LOS MARKETS")).toBeInTheDocument();
    expect(screen.queryByText("ÚLTIMAS MENCIONES")).not.toBeInTheDocument();
  });

  it("uses natural month range and supports month navigation", async () => {
    render(<SentimentView mode="dashboard" />);
    await screen.findByText("Dashboard reputacional");

    const now = new Date();
    const currentStart = toDate(new Date(now.getFullYear(), now.getMonth(), 1));
    const currentEnd = toDate(now);
    const currentLabel = monthLabel(new Date(now.getFullYear(), now.getMonth(), 1));

    expect(screen.getByTestId("dashboard-month-label")).toHaveTextContent(currentLabel);
    expect(screen.getByRole("button", { name: "Mes siguiente" })).toBeDisabled();

    await waitFor(() => {
      const queriedCurrentMonth = apiGetMock.mock.calls.some(([path]) => {
        if (typeof path !== "string") return false;
        return (
          path.startsWith("/reputation/items?") &&
          path.includes(`from_date=${currentStart}`) &&
          path.includes(`to_date=${currentEnd}`)
        );
      });
      expect(queriedCurrentMonth).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "Mes anterior" }));

    const previousDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const previousStart = toDate(previousDate);
    const previousEnd = toDate(
      new Date(previousDate.getFullYear(), previousDate.getMonth() + 1, 0),
    );
    const previousLabel = monthLabel(previousDate);

    await waitFor(() => {
      expect(screen.getByTestId("dashboard-month-label")).toHaveTextContent(previousLabel);
      const queriedPreviousMonth = apiGetMock.mock.calls.some(([path]) => {
        if (typeof path !== "string") return false;
        return (
          path.startsWith("/reputation/items?") &&
          path.includes(`from_date=${previousStart}`) &&
          path.includes(`to_date=${previousEnd}`)
        );
      });
      expect(queriedPreviousMonth).toBe(true);
    });

    expect(screen.getByRole("button", { name: "Mes siguiente" })).not.toBeDisabled();
  });
});

function toDate(d: Date) {
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

function monthLabel(d: Date) {
  const value = new Intl.DateTimeFormat("es-ES", {
    month: "long",
    year: "numeric",
  }).format(d);
  return value.charAt(0).toUpperCase() + value.slice(1);
}
