/** Tests del flujo de Sentimiento (modo vista completa). */

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
  usePathname: () => "/sentimiento",
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiGetCached: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiGetCached, apiPost } from "@/lib/api";
import { INGEST_SUCCESS_EVENT } from "@/lib/events";
import SentimientoPage from "@/app/sentimiento/page";

const apiGetMock = vi.mocked(apiGet);
const apiGetCachedMock = vi.mocked(apiGetCached);
const apiPostMock = vi.mocked(apiPost);

const metaResponse = {
  actor_principal: { canonical: "Acme, Bank", aliases: ["Acme"] },
  geos: ["España", "USA"],
  otros_actores_por_geografia: { "España": ["Beta Bank"] },
  otros_actores_globales: ["Beta Bank"],
  ui_show_comparisons: true,
  sources_enabled: ["news", "appstore", "google_play"],
  sources_available: ["news", "appstore", "google_play"],
  cache_available: false,
  market_ratings: [
    {
      source: "appstore",
      actor: "Acme Bank",
      geo: "España",
      rating: 4.2,
      rating_count: 120,
      collected_at: "2025-01-10T00:00:00Z",
    },
    {
      source: "google_play",
      actor: "Acme Bank",
      geo: "España",
      rating: 3.9,
      rating_count: 90,
      collected_at: "2025-01-11T00:00:00Z",
    },
  ],
  market_ratings_history: [
    {
      source: "appstore",
      actor: "Acme Bank",
      geo: "España",
      rating: 4.0,
      rating_count: 110,
      collected_at: "2024-12-10T00:00:00Z",
    },
  ],
};

const itemsResponse = {
  generated_at: "2025-01-12T00:00:00Z",
  config_hash: "hash",
  sources_enabled: ["news", "appstore", "google_play"],
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
    {
      id: "p2",
      source: "appstore",
      geo: "España",
      actor: "Acme Bank",
      title: "Reseña App",
      text: "Muy bien",
      sentiment: "positive",
      published_at: "2025-01-02T10:00:00Z",
      signals: { rating: 4.5, sentiment_score: 0.4 },
    },
    {
      id: "b1",
      source: "news",
      geo: "España",
      actor: "Beta Bank",
      title: "Beta Bank alerta",
      text: "Incidencia crítica",
      sentiment: "negative",
      published_at: "2025-01-03T10:00:00Z",
    },
    {
      id: "b2",
      source: "google_play",
      geo: "España",
      actor: "Beta Bank",
      title: "Beta Bank caída",
      text: "Baja puntuación",
      sentiment: "negative",
      published_at: "2025-01-04T10:00:00Z",
      signals: { sentiment_score: -0.5 },
    },
  ],
  stats: { count: 4 },
};

const profilesResponse = {
  active: { source: "default", profiles: ["banking"], profile_key: "banking" },
  options: { default: ["banking"], samples: [] },
};

const compareResponse = {
  groups: [
    { id: "principal", filter: {}, items: itemsResponse.items, stats: { count: 2 } },
    { id: "actor", filter: {}, items: itemsResponse.items, stats: { count: 1 } },
  ],
  combined: { items: itemsResponse.items, stats: { count: 3 } },
};

describe("Sentimiento page", () => {
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
      return Promise.resolve({ items: [] });
    };
    apiGetMock.mockImplementation(handleGet);
    apiGetCachedMock.mockImplementation(handleGet);
    apiPostMock.mockImplementation((path: string) => {
      if (path === "/reputation/items/compare") {
        return Promise.resolve(compareResponse);
      }
      if (path === "/reputation/items/override") {
        return Promise.resolve({ updated: 1 });
      }
      if (path === "/ingest/reputation") {
        return Promise.resolve({ id: "job-1", kind: "reputation", status: "queued", progress: 0 });
      }
      return Promise.resolve({});
    });
  });

  it("renders sentiment view with filters, overrides, and download", async () => {
    if (!("createObjectURL" in URL)) {
      Object.defineProperty(URL, "createObjectURL", {
        value: vi.fn(() => "blob:mock"),
        configurable: true,
      });
    }
    if (!("revokeObjectURL" in URL)) {
      Object.defineProperty(URL, "revokeObjectURL", {
        value: vi.fn(),
        configurable: true,
      });
    }
    const createUrlSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
    const revokeUrlSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const anchorClickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    render(<SentimientoPage />);

    expect(await screen.findByText("Sentimiento histórico")).toBeInTheDocument();

    await screen.findByRole("option", { name: "España" });
    const geoSelect = screen.getByLabelText("País");
    fireEvent.change(geoSelect, { target: { value: "España" } });

    fireEvent.click(screen.getByText("Descargar gráfico"));

    const adjustButtons = await screen.findAllByText("Ajustar");
    fireEvent.click(adjustButtons[0]);

    const geoInput = screen.getByPlaceholderText("Ej: España");
    fireEvent.change(geoInput, { target: { value: "USA" } });

    fireEvent.click(screen.getByText("Guardar ajuste"));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        "/reputation/items/override",
        expect.anything()
      );
    });

    fireEvent.click(screen.getByText("Descargar listado"));
    expect(createUrlSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByText("Iniciar ingesta"));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith("/ingest/reputation", {
        force: false,
        all_sources: false,
      });
    });

    window.dispatchEvent(
      new CustomEvent(INGEST_SUCCESS_EVENT, { detail: { kind: "reputation" } })
    );

    createUrlSpy.mockRestore();
    revokeUrlSpy.mockRestore();
    anchorClickSpy.mockRestore();
  });

  it("requests comparison when selecting another actor", async () => {
    render(<SentimientoPage />);

    expect(await screen.findByText("Sentimiento histórico")).toBeInTheDocument();

    const geoSelect = screen.getByLabelText("País");
    fireEvent.change(geoSelect, { target: { value: "España" } });

    const actorSelect = screen.getByLabelText("Otros actores del mercado");
    fireEvent.change(actorSelect, { target: { value: "Beta Bank" } });

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        "/reputation/items/compare",
        expect.anything()
      );
    });
  });
});
