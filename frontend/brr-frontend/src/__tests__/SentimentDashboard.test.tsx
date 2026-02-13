/** Tests del modo dashboard de SentimentView. */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  waitForElementToBeRemoved,
  within,
} from "@testing-library/react";
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
    expect(await screen.findByText("MAPA DE CALOR DE OPINIONES NEGATIVAS EN LOS MARKETS")).toBeInTheDocument();
    expect(screen.queryByText("ÚLTIMAS MENCIONES")).not.toBeInTheDocument();
  });

  it("renders heatmap between filtros principales and sentimiento chart", async () => {
    render(<SentimentView mode="dashboard" />);

    const filtros = await screen.findByText("FILTROS PRINCIPALES");
    const heatmap = await screen.findByText("MAPA DE CALOR DE OPINIONES NEGATIVAS EN LOS MARKETS");
    const sentimiento = await screen.findByText("SENTIMIENTO");

    expect(Boolean(filtros.compareDocumentPosition(heatmap) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
    expect(Boolean(heatmap.compareDocumentPosition(sentimiento) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
  });

  it("uses contestable-opinions denominator and excludes downdetector from heat rows", async () => {
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
            opinions_total: 42,
            answered_total: 0,
            answered_ratio: 0,
            answered_positive: 0,
            answered_neutral: 0,
            answered_negative: 0,
            unanswered_positive: 0,
            unanswered_neutral: 0,
            unanswered_negative: 42,
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
            total_mentions: 42,
            negative_mentions: 35,
            negative_ratio: 35 / 42,
            positive_mentions: 7,
            neutral_mentions: 0,
            unique_authors: 10,
            recurring_authors: 0,
            average_sentiment_score: -0.4,
          },
          daily_volume: [{ date: "2025-01-01", count: 42 }],
          geo_summary: [],
          recurring_authors: [],
          top_penalized_features: [{ feature: "login", key: "login", count: 3, evidence: [] }],
          source_friction: [
            {
              source: "google_play",
              total: 2,
              negative: 2,
              positive: 0,
              neutral: 0,
              negative_ratio: 1,
              top_features: [],
            },
            {
              source: "downdetector",
              total: 1,
              negative: 1,
              positive: 0,
              neutral: 0,
              negative_ratio: 1,
              top_features: [],
            },
            {
              source: "appstore",
              total: 39,
              negative: 32,
              positive: 7,
              neutral: 0,
              negative_ratio: 32 / 39,
              top_features: [],
            },
          ],
          response_source_friction: [
            {
              source: "appstore",
              total: 39,
              negative: 32,
              positive: 7,
              neutral: 0,
              negative_ratio: 32 / 42,
              top_features: [],
            },
            {
              source: "google_play",
              total: 2,
              negative: 2,
              positive: 0,
              neutral: 0,
              negative_ratio: 2 / 42,
              top_features: [],
            },
          ],
          downdetector_incidents: 1,
          alerts: [],
          responses: {
            totals: {
              opinions_total: 42,
              answered_total: 0,
              answered_ratio: 0,
              answered_positive: 0,
              answered_neutral: 0,
              answered_negative: 0,
              unanswered_positive: 0,
              unanswered_neutral: 0,
              unanswered_negative: 42,
            },
            actor_breakdown: [],
            repeated_replies: [],
            answered_items: [],
          },
        });
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({});
    };

    apiGetMock.mockImplementation(handleGet);
    apiGetCachedMock.mockImplementation(handleGet);

    render(<SentimentView mode="dashboard" />);

    const heatmapTitle = screen.getByText("MAPA DE CALOR DE OPINIONES NEGATIVAS EN LOS MARKETS");
    const heatmapSection = heatmapTitle.closest("section");
    expect(heatmapSection).not.toBeNull();

    const sectionQueries = within(heatmapSection as HTMLElement);
    const loadingPills = sectionQueries.queryAllByText("Cargando canales");
    if (loadingPills.length > 0) {
      await waitForElementToBeRemoved(loadingPills, { timeout: 7000 });
    }

    const ratioRows = await waitFor(
      () => sectionQueries.getAllByText(/^\d+\/\d+ negativas \(\d+\.\d%\)$/),
      { timeout: 7000 }
    );
    const ratioTexts = ratioRows.map((row) => row.textContent?.trim() ?? "");
    const parseRatio = (text: string) => {
      const match = /^(\d+)\/(\d+) negativas \((\d+\.\d)%\)$/.exec(text);
      expect(match).not.toBeNull();
      return {
        negative: Number(match?.[1] ?? 0),
        total: Number(match?.[2] ?? 0),
        percent: Number(match?.[3] ?? 0),
      };
    };
    const topRatio = parseRatio(ratioTexts[0] ?? "");
    const secondRatio = parseRatio(ratioTexts[1] ?? "");
    expect(topRatio.negative).toBe(32);
    expect(secondRatio.negative).toBe(2);
    expect(topRatio.total).toBe(secondRatio.total);
    expect(topRatio.percent).toBeGreaterThan(secondRatio.percent);
    expect(sectionQueries.queryByText(/1\/\d+ negativas \(\d+\.\d%\)/)).not.toBeInTheDocument();
    expect(sectionQueries.queryByText(/Downdetector ha identificado/i)).not.toBeInTheDocument();
  });

  it("renders dashboard summary with actor mentions, market responses ratios and response coverage percent", async () => {
    const handleGet = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve({
          ...metaResponse,
          ui_show_dashboard_responses: true,
          sources_enabled: ["appstore", "google_play"],
          sources_available: ["appstore", "google_play"],
          market_ratings: [
            {
              source: "appstore",
              actor: "Acme Bank",
              geo: "España",
              rating: 4.12,
              rating_count: 120,
              collected_at: "2025-01-01T00:00:00Z",
            },
            {
              source: "google_play",
              actor: "Acme Bank",
              geo: "España",
              rating: 4.6,
              rating_count: 240,
              collected_at: "2025-01-01T00:00:00Z",
            },
          ],
        });
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve({
          ...itemsResponse,
          sources_enabled: ["appstore", "google_play"],
          items: [
            {
              id: "dash-1",
              source: "appstore",
              geo: "España",
              actor: "Acme Bank",
              title: "Muy buena",
              text: "Me gusta la app",
              sentiment: "positive",
              published_at: "2025-01-01T10:00:00Z",
              signals: {
                sentiment_score: 0.6,
                reply_text: "Gracias por tu comentario",
              },
            },
            {
              id: "dash-2",
              source: "google_play",
              geo: "España",
              actor: "Acme Bank",
              title: "Puede mejorar",
              text: "Regular",
              sentiment: "neutral",
              published_at: "2025-01-02T10:00:00Z",
              signals: { sentiment_score: 0.0 },
            },
            {
              id: "dash-3",
              source: "google_play",
              geo: "España",
              actor: "Acme Bank",
              title: "Mala experiencia",
              text: "No funciona",
              sentiment: "negative",
              published_at: "2025-01-03T10:00:00Z",
              signals: {
                sentiment_score: -0.8,
                reply_text: "Estamos revisándolo",
              },
            },
          ],
          stats: { count: 3 },
        });
      }
      if (path.startsWith("/reputation/responses/summary")) {
        return Promise.resolve({
          totals: {
            opinions_total: 3,
            answered_total: 2,
            answered_ratio: 2 / 3,
            answered_positive: 1,
            answered_neutral: 0,
            answered_negative: 1,
            unanswered_positive: 0,
            unanswered_neutral: 1,
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
            total_mentions: 3,
            negative_mentions: 1,
            negative_ratio: 1 / 3,
            positive_mentions: 1,
            neutral_mentions: 1,
            unique_authors: 3,
            recurring_authors: 0,
            average_sentiment_score: -0.07,
          },
          daily_volume: [{ date: "2025-01-01", count: 3 }],
          geo_summary: [],
          recurring_authors: [],
          top_penalized_features: [{ feature: "login", key: "login", count: 2, evidence: [] }],
          source_friction: [],
          alerts: [],
          responses: undefined,
        });
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({});
    };

    apiGetMock.mockImplementation(handleGet);
    apiGetCachedMock.mockImplementation(handleGet);

    render(<SentimentView mode="dashboard" />);

    const mentionsBlock = await screen.findByText("Menciones actor principal");
    const ratingBlock = await screen.findByText("Rating oficial");
    const responsesBlock = await screen.findByText("opiniones del market contestadas");
    expect(Boolean(mentionsBlock.compareDocumentPosition(ratingBlock) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
    expect(Boolean(ratingBlock.compareDocumentPosition(responsesBlock) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);

    const summarySection = mentionsBlock.closest("section");
    expect(summarySection).toBeTruthy();
    expect((summarySection?.textContent || "").includes("Score medio")).toBe(false);

    expect(await screen.findByText("opiniones del market contestadas")).toBeInTheDocument();
    expect(screen.getByText("Apple")).toBeInTheDocument();
    expect(screen.getByText("Android")).toBeInTheDocument();
    expect(screen.getByText("Score medio")).toBeInTheDocument();

    const responsesTitle = screen.getByTestId("responses-summary-title");
    expect(responsesTitle).toHaveTextContent("2/3");
    const responsesCard = responsesTitle.parentElement?.parentElement;
    expect(responsesCard).toBeTruthy();
    expect((responsesCard?.textContent || "").includes("1/1")).toBe(true);
    expect((responsesCard?.textContent || "").includes("0/1")).toBe(true);
    expect((responsesCard?.textContent || "").includes("66.7%")).toBe(true);
    expect((responsesCard?.textContent || "").includes("(2/3)")).toBe(false);
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
