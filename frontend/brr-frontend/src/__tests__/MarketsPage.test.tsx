/** Tests de la navegación Markets Intelligence. */

import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/markets",
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiGetCached: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiGetCached } from "@/lib/api";
import MarketsPage from "@/app/markets/page";

const apiGetMock = vi.mocked(apiGet);
const apiGetCachedMock = vi.mocked(apiGetCached);

describe("MarketsPage", () => {
  beforeEach(() => {
    const handleGet = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve({
          actor_principal: { canonical: "Acme Bank" },
          geos: ["ES", "MX"],
          sources_enabled: ["news", "appstore"],
          sources_available: ["news", "appstore"],
          cache_available: true,
        });
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve({
          active: { source: "default", profiles: ["banking"], profile_key: "banking" },
          options: { default: ["banking"], samples: ["banking"] },
        });
      }
      if (path.startsWith("/reputation/markets/insights")) {
        return Promise.resolve({
          generated_at: "2026-02-13T12:00:00Z",
          principal_actor: "Acme Bank",
          comparisons_enabled: false,
          filters: { geo: "all", from_date: "2026-01-15", to_date: "2026-02-13", sources: [] },
          kpis: {
            total_mentions: 12,
            negative_mentions: 5,
            negative_ratio: 0.4167,
            positive_mentions: 3,
            neutral_mentions: 4,
            unique_authors: 7,
            recurring_authors: 2,
            average_sentiment_score: -0.13,
          },
          daily_volume: [{ date: "2026-02-13", count: 3 }],
          geo_summary: [
            {
              geo: "ES",
              total: 9,
              negative: 4,
              positive: 2,
              neutral: 3,
              negative_ratio: 0.4444,
              share: 0.75,
            },
          ],
          recurring_authors: [
            {
              author: "Ana",
              opinions_count: 3,
              sentiments: { negative: 2, neutral: 1, positive: 0 },
              last_seen: "2026-02-13T11:00:00Z",
              opinions: [
                {
                  id: "a1",
                  author: "ana_1989",
                  source: "appstore",
                  geo: "ES",
                  sentiment: "negative",
                  published_at: "2026-02-13T10:00:00Z",
                  title: "Fallo login",
                  excerpt: "No me deja entrar",
                },
              ],
            },
          ],
          top_penalized_features: [
            {
              feature: "login",
              key: "login",
              count: 4,
              evidence: [
                {
                  id: "a1",
                  source: "appstore",
                  geo: "ES",
                  sentiment: "negative",
                  published_at: "2026-02-13T10:00:00Z",
                  title: "Fallo login",
                },
              ],
            },
          ],
          source_friction: [
            {
              source: "appstore",
              total: 6,
              negative: 4,
              positive: 1,
              neutral: 1,
              negative_ratio: 0.6667,
              top_features: [{ feature: "login", count: 3 }],
            },
          ],
          alerts: [
            {
              id: "source-appstore",
              severity: "high",
              title: "Fuente bajo presión: appstore",
              summary: "4/6 menciones negativas.",
              geo: "all",
              source: "appstore",
              evidence_ids: [],
            },
          ],
          responses: {
            totals: {
              opinions_total: 12,
              answered_total: 6,
              answered_ratio: 0.5,
              answered_positive: 2,
              answered_neutral: 1,
              answered_negative: 3,
              unanswered_positive: 1,
              unanswered_neutral: 3,
              unanswered_negative: 2,
            },
            actor_breakdown: [
              {
                actor: "Acme Bank",
                actor_type: "principal",
                answered: 6,
                answered_positive: 2,
                answered_neutral: 1,
                answered_negative: 3,
              },
            ],
            repeated_replies: [
              {
                reply_text: "Gracias por reportarlo",
                count: 3,
                actors: [{ actor: "Acme Bank", count: 3 }],
                sentiments: { positive: 1, neutral: 0, negative: 2, unknown: 0 },
                sample_item_ids: ["a1"],
              },
            ],
            answered_items: [],
          },
          newsletter_by_geo: [
            {
              geo: "ES",
              subject: "[GOR] Radar reputacional ES · 2026-02-13",
              preview: "4/9 negativas",
              markdown: "# Newsletter reputacional · ES\n\n## Señales clave",
              actions: ["Activar plan de choque en login."],
            },
          ],
        });
      }
      return Promise.resolve({});
    };
    apiGetMock.mockImplementation(handleGet);
    apiGetCachedMock.mockImplementation(handleGet);
  });

  it("renders wow markets page with insights and newsletter", async () => {
    render(<MarketsPage />);

    expect(await screen.findByText("Wow Radar de mercado")).toBeInTheDocument();
    expect(await screen.findByText("Voces insistentes")).toBeInTheDocument();
    expect(await screen.findByText("Newsletter por geografía")).toBeInTheDocument();
    expect(await screen.findByText("Respuestas oficiales")).toBeInTheDocument();
    expect(screen.queryByText("Top 10 funcionalidades penalizadas")).not.toBeInTheDocument();
    expect(screen.queryByText("Fricción por canal")).not.toBeInTheDocument();
    expect(screen.queryByText("Alertas calientes")).not.toBeInTheDocument();
    expect(await screen.findByText("Ana")).toBeInTheDocument();
    expect(await screen.findByText("Autor: ana_1989")).toBeInTheDocument();
    expect(await screen.findByText("ID: a1")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Copiar"));
    expect((await screen.findAllByText("Markets WoW")).length).toBeGreaterThan(0);
  });
});
