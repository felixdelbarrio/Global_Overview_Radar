/** Tests del modo dashboard de SentimentView. */

import React from "react";
import { render, screen } from "@testing-library/react";
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
  });
});
