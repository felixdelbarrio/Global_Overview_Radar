/** Tests del flujo de Sentimiento (modo vista completa). */

import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
import { INGEST_SUCCESS_EVENT, SETTINGS_CHANGED_EVENT } from "@/lib/events";
import SentimientoPage from "@/app/sentimiento/page";
import { SentimentView } from "@/components/SentimentView";

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
      author: "Alexis",
      title: "Reseña App",
      text: "Muy bien",
      sentiment: "positive",
      published_at: "2025-01-02T10:00:00Z",
      signals: {
        rating: 4.5,
        sentiment_score: 0.4,
        reply_text: "Gracias por tu comentario",
        reply_author: "Soporte BBVA",
      },
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
      author: "Marina",
      title: "Beta Bank caída",
      text: "Baja puntuación",
      sentiment: "negative",
      published_at: "2025-01-04T10:00:00Z",
      signals: {
        sentiment_score: -0.5,
        reply_text: "Lamentamos la incidencia",
        reply_author: "Beta Support",
      },
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
      if (path.startsWith("/reputation/responses/summary")) {
        const isPrincipalSummary = path.includes("entity=actor_principal");
        if (isPrincipalSummary) {
          return Promise.resolve({
            totals: {
              opinions_total: 4,
              answered_total: 2,
              answered_ratio: 0.5,
              answered_positive: 1,
              answered_neutral: 1,
              answered_negative: 0,
              unanswered_positive: 0,
              unanswered_neutral: 1,
              unanswered_negative: 1,
            },
            actor_breakdown: [],
            repeated_replies: [],
            answered_items: [
              {
                id: "rp1",
                source: "appstore",
                geo: "España",
                sentiment: "neutral",
                actor: "Acme Bank",
                actor_canonical: "Acme Bank",
                responder_actor: "Acme Bank",
                responder_actor_type: "principal",
                reply_text: "Gracias por tu comentario. Estamos revisando.",
                reply_excerpt: "Neutra principal",
                reply_author: "Acme Soporte",
                replied_at: "2025-01-03T10:30:00Z",
                published_at: "2025-01-03T10:00:00Z",
                title: "Reseña App",
                url: null,
              },
              {
                id: "rp2",
                source: "google_play",
                geo: "España",
                sentiment: "positive",
                actor: "Acme Bank",
                actor_canonical: "Acme Bank",
                responder_actor: "Acme Bank",
                responder_actor_type: "principal",
                reply_text: "Nos alegra que te haya servido.",
                reply_excerpt: "Positiva principal",
                reply_author: "Acme Soporte",
                replied_at: "2025-01-02T10:30:00Z",
                published_at: "2025-01-02T10:00:00Z",
                title: "Muy útil",
                url: null,
              },
            ],
          });
        }
        return Promise.resolve({
          totals: {
            opinions_total: 6,
            answered_total: 3,
            answered_ratio: 0.5,
            answered_positive: 0,
            answered_neutral: 2,
            answered_negative: 1,
            unanswered_positive: 1,
            unanswered_neutral: 1,
            unanswered_negative: 1,
          },
          actor_breakdown: [],
          repeated_replies: [],
          answered_items: [
            {
              id: "ro1",
              source: "appstore",
              geo: "España",
              sentiment: "neutral",
              actor: "Beta Bank",
              actor_canonical: "Beta Bank",
              responder_actor: "Beta Bank",
              responder_actor_type: "secondary",
              reply_text: "Seguimos tu caso.",
              reply_excerpt: "Neutra beta 1",
              reply_author: "Beta Support",
              replied_at: "2025-01-04T12:30:00Z",
              published_at: "2025-01-04T12:00:00Z",
              title: "Neutra beta 1",
              url: null,
            },
            {
              id: "ro2",
              source: "google_play",
              geo: "España",
              sentiment: "neutral",
              actor: "Beta Bank",
              actor_canonical: "Beta Bank",
              responder_actor: "Beta Bank",
              responder_actor_type: "secondary",
              reply_text: "Te escribimos por privado.",
              reply_excerpt: "Neutra beta 2",
              reply_author: "Beta Support",
              replied_at: "2025-01-05T08:30:00Z",
              published_at: "2025-01-05T08:00:00Z",
              title: "Neutra beta 2",
              url: null,
            },
            {
              id: "ro3",
              source: "google_play",
              geo: "España",
              sentiment: "negative",
              actor: "Beta Bank",
              actor_canonical: "Beta Bank",
              responder_actor: "Beta Bank",
              responder_actor_type: "secondary",
              reply_text: "Lamentamos la incidencia.",
              reply_excerpt: "Negativa beta",
              reply_author: "Beta Support",
              replied_at: "2025-01-05T09:30:00Z",
              published_at: "2025-01-05T09:00:00Z",
              title: "Negativa beta",
              url: null,
            },
          ],
        });
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

  it("renders sentiment view with filters, without manual controls in markets, and download", async () => {
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

    await screen.findByLabelText("País");
    await screen.findByRole("option", { name: "España" });
    const geoSelect = screen.getByLabelText("País");
    fireEvent.change(geoSelect, { target: { value: "España" } });

    const responsesHeading = await screen.findByTestId("responses-summary-title");
    const responsesCard = responsesHeading.parentElement;
    expect(responsesCard).toBeTruthy();
    expect(responsesHeading).toHaveTextContent(/Acme/i);
    expect(responsesHeading).toHaveTextContent(/1\/1/i);
    expect(responsesHeading).toHaveTextContent(/opiniones del market contestadas/i);
    expect(within(responsesCard as HTMLElement).getByText("Positivas")).toBeInTheDocument();
    expect(within(responsesCard as HTMLElement).queryByText(/^Total$/i)).not.toBeInTheDocument();
    expect(within(responsesCard as HTMLElement).queryByText("Comentarios contestados")).not.toBeInTheDocument();
    const summarySection = screen.getByText("RESUMEN").closest("section");
    expect(summarySection).toBeTruthy();
    expect(within(summarySection as HTMLElement).queryByText("Score medio")).not.toBeInTheDocument();

    const mentionList = screen.getByText("LISTADO").closest("section");
    expect(mentionList).toBeTruthy();
    expect(within(mentionList as HTMLElement).getByText("CONTESTACION")).toBeInTheDocument();
    expect(within(mentionList as HTMLElement).getByText("Gracias por tu comentario")).toBeInTheDocument();
    expect(within(mentionList as HTMLElement).getByText("Soporte BBVA")).toBeInTheDocument();
    expect(within(mentionList as HTMLElement).getByText("Alexis")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Otros actores del mercado/i }));
    expect(within(mentionList as HTMLElement).getByText("Lamentamos la incidencia")).toBeInTheDocument();

    const listedFilters = within(mentionList as HTMLElement).getByText(/SENTIMIENTO:/i);
    expect(listedFilters).toBeInTheDocument();
    expect(listedFilters).toHaveTextContent(/PAÍS: España/i);
    expect(listedFilters).toHaveTextContent(/SENTIMIENTO: Todos/i);
    expect(responsesHeading).not.toHaveTextContent(/vs/i);

    fireEvent.click(screen.getByText("Descargar gráfico"));

    await waitFor(() => {
      expect(screen.queryByText("Control manual")).not.toBeInTheDocument();
      expect(screen.queryByText("Ajustar")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Descargar listado"));
    expect(createUrlSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Centro de ingestas"));
    expect(await screen.findByText("CENTRO DE INGESTA")).toBeInTheDocument();
    fireEvent.click(screen.getAllByText("Iniciar ingesta")[0]);
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

    await screen.findByLabelText("País");
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

    const responsesCard = await screen.findByTestId("responses-summary-title");
    const container = responsesCard.parentElement?.parentElement;
    expect(container).toBeTruthy();
    expect(within(container as HTMLElement).queryByText("Actor secundario")).not.toBeInTheDocument();
    expect(within(container as HTMLElement).getAllByText("Beta Bank").length).toBeGreaterThan(0);
  });

  it("shows all market actors with source legend in the actors table", async () => {
    const marketMetaResponse = {
      ...metaResponse,
      sources_enabled: ["appstore", "google_play", "downdetector"],
      sources_available: ["appstore", "google_play", "downdetector"],
      ui_show_comparisons: true,
    };
    const marketItemsResponse = {
      ...itemsResponse,
      sources_enabled: ["appstore", "google_play", "downdetector"],
      items: [
        {
          id: "principal-1",
          source: "appstore",
          geo: "España",
          actor: "Acme Bank",
          title: "Principal",
          text: "Principal",
          sentiment: "neutral",
          published_at: "2025-01-01T10:00:00Z",
        },
        {
          id: "rev-1",
          source: "appstore",
          geo: "España",
          actor: "Revolut",
          title: "Revolut 1",
          text: "Revolut 1",
          sentiment: "negative",
          published_at: "2025-01-02T10:00:00Z",
        },
        {
          id: "rev-2",
          source: "google_play",
          geo: "España",
          actor: "Revolut",
          title: "Revolut 2",
          text: "Revolut 2",
          sentiment: "negative",
          published_at: "2025-01-03T10:00:00Z",
        },
        {
          id: "rev-3",
          source: "downdetector",
          geo: "España",
          actor: "Revolut",
          title: "Revolut 3",
          text: "Revolut 3",
          sentiment: "negative",
          published_at: "2025-01-04T10:00:00Z",
        },
        {
          id: "caixa-1",
          source: "google_play",
          geo: "España",
          actor: "CaixaBank",
          title: "Caixa 1",
          text: "Caixa 1",
          sentiment: "negative",
          published_at: "2025-01-05T10:00:00Z",
        },
        {
          id: "caixa-2",
          source: "google_play",
          geo: "España",
          actor: "CaixaBank",
          title: "Caixa 2",
          text: "Caixa 2",
          sentiment: "negative",
          published_at: "2025-01-06T10:00:00Z",
        },
        {
          id: "open-1",
          source: "appstore",
          geo: "España",
          actor: "Openbank",
          title: "Openbank 1",
          text: "Openbank 1",
          sentiment: "negative",
          published_at: "2025-01-07T10:00:00Z",
        },
        {
          id: "wise-1",
          source: "downdetector",
          geo: "España",
          actor: "Wise",
          title: "Wise 1",
          text: "Wise 1",
          sentiment: "negative",
          published_at: "2025-01-08T10:00:00Z",
        },
        {
          id: "sabadell-1",
          source: "appstore",
          geo: "España",
          actor: "Sabadell",
          title: "Sabadell 1",
          text: "Sabadell 1",
          sentiment: "negative",
          published_at: "2025-01-09T10:00:00Z",
        },
        {
          id: "sabadell-2",
          source: "downdetector",
          geo: "España",
          actor: "Sabadell",
          title: "Sabadell 2",
          text: "Sabadell 2",
          sentiment: "negative",
          published_at: "2025-01-10T10:00:00Z",
        },
        {
          id: "n26-1",
          source: "google_play",
          geo: "España",
          actor: "N26",
          title: "N26 1",
          text: "N26 1",
          sentiment: "negative",
          published_at: "2025-01-11T10:00:00Z",
        },
      ],
      stats: { count: 11 },
    };

    const handleGetMarketActors = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(marketMetaResponse);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(marketItemsResponse);
      }
      if (path.startsWith("/reputation/responses/summary")) {
        return Promise.resolve({
          totals: {
            opinions_total: 0,
            answered_total: 0,
            answered_ratio: 0,
            answered_positive: 0,
            answered_neutral: 0,
            answered_negative: 0,
            unanswered_positive: 0,
            unanswered_neutral: 0,
            unanswered_negative: 0,
          },
          actor_breakdown: [],
          repeated_replies: [],
          answered_items: [],
        });
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({ items: [] });
    };

    apiGetMock.mockImplementation(handleGetMarketActors);
    apiGetCachedMock.mockImplementation(handleGetMarketActors);

    render(<SentimentView mode="sentiment" scope="all" />);

    await screen.findByLabelText("País");

    await waitFor(() => {
      expect(screen.queryByText("TOP OTROS ACTORES DEL MERCADO")).not.toBeInTheDocument();
      const actorsTitle = screen.getByText("ACTORES DEL MERCADO");
      const actorsBlock = actorsTitle.parentElement;
      expect(actorsBlock).toBeTruthy();
      expect(within(actorsBlock as HTMLElement).getByText("App Store (4)")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Google Play (4)")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Acme Bank")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Revolut")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("CaixaBank")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Openbank")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Sabadell")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("N26")).toBeInTheDocument();
    });
  });

  it("filters actors table and legend to the selected secondary actor", async () => {
    const actorScopedMetaResponse = {
      ...metaResponse,
      ui_show_comparisons: true,
      sources_enabled: ["appstore", "google_play", "downdetector"],
      sources_available: ["appstore", "google_play", "downdetector"],
      otros_actores_por_geografia: {
        España: ["Santander", "CaixaBank"],
      },
      otros_actores_globales: ["Santander", "CaixaBank"],
    };

    const actorScopedItemsResponse = {
      ...itemsResponse,
      sources_enabled: ["appstore", "google_play", "downdetector"],
      items: [
        {
          id: "principal-1",
          source: "appstore",
          geo: "España",
          actor: "Acme Bank",
          title: "Principal",
          text: "Principal",
          sentiment: "neutral",
          published_at: "2025-01-01T10:00:00Z",
        },
        {
          id: "santander-1",
          source: "appstore",
          geo: "España",
          actor: "Santander",
          title: "Santander appstore",
          text: "Santander appstore",
          sentiment: "negative",
          published_at: "2025-01-02T10:00:00Z",
        },
        {
          id: "santander-2",
          source: "downdetector",
          geo: "España",
          actor: "Santander",
          title: "Santander down",
          text: "Santander down",
          sentiment: "negative",
          published_at: "2025-01-03T10:00:00Z",
        },
        {
          id: "caixa-1",
          source: "google_play",
          geo: "España",
          actor: "CaixaBank",
          title: "Caixa play",
          text: "Caixa play",
          sentiment: "negative",
          published_at: "2025-01-04T10:00:00Z",
        },
      ],
      stats: { count: 4 },
    };

    const compareItemsResponse = {
      groups: [],
      combined: {
        items: [
          {
            id: "principal-compare",
            source: "appstore",
            geo: "España",
            actor: "Acme Bank",
            title: "Principal compare",
            text: "Principal compare",
            sentiment: "neutral",
            published_at: "2025-01-05T10:00:00Z",
          },
          {
            id: "santander-compare-1",
            source: "appstore",
            geo: "España",
            actor: "Santander",
            title: "Santander compare 1",
            text: "Santander compare 1",
            sentiment: "negative",
            published_at: "2025-01-06T10:00:00Z",
          },
          {
            id: "santander-compare-2",
            source: "downdetector",
            geo: "España",
            actor: "Santander",
            title: "Santander compare 2",
            text: "Santander compare 2",
            sentiment: "negative",
            published_at: "2025-01-07T10:00:00Z",
          },
          {
            id: "caixa-compare-1",
            source: "google_play",
            geo: "España",
            actor: "CaixaBank",
            title: "Caixa compare 1",
            text: "Caixa compare 1",
            sentiment: "negative",
            published_at: "2025-01-08T10:00:00Z",
          },
        ],
        stats: { count: 4 },
      },
    };

    const handleGetActorScoped = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(actorScopedMetaResponse);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(actorScopedItemsResponse);
      }
      if (path.startsWith("/reputation/responses/summary")) {
        return Promise.resolve({
          totals: {
            opinions_total: 0,
            answered_total: 0,
            answered_ratio: 0,
            answered_positive: 0,
            answered_neutral: 0,
            answered_negative: 0,
            unanswered_positive: 0,
            unanswered_neutral: 0,
            unanswered_negative: 0,
          },
          actor_breakdown: [],
          repeated_replies: [],
          answered_items: [],
        });
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({ items: [] });
    };

    apiGetMock.mockImplementation(handleGetActorScoped);
    apiGetCachedMock.mockImplementation(handleGetActorScoped);
    apiPostMock.mockImplementation((path: string) => {
      if (path === "/reputation/items/compare") {
        return Promise.resolve(compareItemsResponse);
      }
      if (path === "/reputation/items/override") {
        return Promise.resolve({ updated: 1 });
      }
      if (path === "/ingest/reputation") {
        return Promise.resolve({ id: "job-1", kind: "reputation", status: "queued", progress: 0 });
      }
      return Promise.resolve({});
    });

    render(<SentimentView mode="sentiment" scope="all" />);

    const actorSelect = (await screen.findByLabelText(
      "Otros actores del mercado",
    )) as HTMLSelectElement;
    fireEvent.change(actorSelect, { target: { value: "Santander" } });

    await waitFor(() => {
      const actorsBlock = screen.getByText("ACTORES DEL MERCADO").parentElement;
      expect(actorsBlock).toBeTruthy();
      expect(within(actorsBlock as HTMLElement).getByText("Acme Bank")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Santander")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).queryByText("CaixaBank")).not.toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("App Store (2)")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Google Play (0)")).toBeInTheDocument();
    });
  });

  it("hides market ratings in press scope", async () => {
    render(<SentimentView mode="sentiment" scope="press" />);

    expect(await screen.findByText("Sentimiento en Prensa")).toBeInTheDocument();

    await screen.findByRole("option", { name: "España" });
    const geoSelect = screen.getByLabelText("País");
    fireEvent.change(geoSelect, { target: { value: "España" } });

    await waitFor(() => {
      expect(screen.queryByText("Rating oficial")).not.toBeInTheDocument();
      expect(screen.queryByText("Rating oficial otros actores")).not.toBeInTheDocument();
      expect(screen.queryByText("ACTORES DEL MERCADO")).not.toBeInTheDocument();
      expect(screen.getByText("MEDIOS EN PRENSA")).toBeInTheDocument();
    });

    const summarySection = screen.getByText("RESUMEN").closest("section");
    expect(summarySection).toBeTruthy();
    expect(within(summarySection as HTMLElement).queryByText("Score medio")).not.toBeInTheDocument();
    expect(within(summarySection as HTMLElement).queryByText("Total menciones")).not.toBeInTheDocument();
    expect(within(summarySection as HTMLElement).getByText(/menciones del/i)).toBeInTheDocument();
  });

  it("shows publisher chip in press mention cards", async () => {
    const metaPressResponse = {
      ...metaResponse,
      sources_enabled: ["news"],
      sources_available: ["news"],
    };
    const itemsPressResponse = {
      ...itemsResponse,
      sources_enabled: ["news"],
      items: [
        {
          id: "press-chip-1",
          source: "news",
          geo: "España",
          actor: "Acme Bank",
          title: "Nueva funcionalidad móvil para empresas",
          text: "Cobertura del lanzamiento en prensa económica.",
          sentiment: "positive",
          published_at: "2025-01-01T10:00:00Z",
          signals: {
            publisher_name: "El Diario Financiero",
          },
          url: "https://example.com/noticia",
        },
      ],
      stats: { count: 1 },
    };

    const handleGetPressPublisherChip = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(metaPressResponse);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(itemsPressResponse);
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({ items: [] });
    };

    apiGetMock.mockImplementation(handleGetPressPublisherChip);
    apiGetCachedMock.mockImplementation(handleGetPressPublisherChip);

    render(<SentimentView mode="sentiment" scope="press" />);

    const cardTitle = await screen.findByText("Nueva funcionalidad móvil para empresas");
    const mentionCard = cardTitle.closest("article");
    expect(mentionCard).toBeTruthy();
    expect(
      within(mentionCard as HTMLElement).getByText("El Diario Financiero")
    ).toBeInTheDocument();
  });

  it("shows press publishers including downdetector and inferred news media", async () => {
    const metaPressResponse = {
      ...metaResponse,
      sources_enabled: ["news", "downdetector"],
      sources_available: ["news", "downdetector"],
    };
    const itemsPressResponse = {
      ...itemsResponse,
      sources_enabled: ["news", "downdetector"],
      items: [
        {
          id: "press-news-1",
          source: "news",
          geo: "España",
          actor: "Acme Bank",
          title:
            "Torres y Genç perciben un 3% menos de remuneración en 2025 pese al beneficio récord de BBVA - eleconomista.es",
          text:
            '<a href="https://news.google.com/rss/articles/abc?oc=5">Torres y Genç perciben un 3% menos de remuneración en 2025 pese al beneficio récord de BBVA</a>&nbsp;&nbsp;<font color="#6f6f6f">eleconomista.es</font>',
          sentiment: "negative",
          published_at: "2025-01-01T10:00:00Z",
          signals: { source: "Google News" },
          url: "https://news.google.com/rss/articles/abc?oc=5",
        },
        {
          id: "press-dd-1",
          source: "downdetector",
          geo: "España",
          actor: "Acme Bank",
          title: "Usuarios reportan incidencias de acceso",
          text: "Múltiples usuarios reportan problemas de login.",
          sentiment: "neutral",
          published_at: "2025-01-02T10:00:00Z",
          signals: {
            publisher_name: "Downdetector",
            publisher_domain: "downdetector.es",
          },
          url: "https://downdetector.es",
        },
      ],
      stats: { count: 2 },
    };

    const handleGetPressPublishers = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(metaPressResponse);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(itemsPressResponse);
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({ items: [] });
    };

    apiGetMock.mockImplementation(handleGetPressPublishers);
    apiGetCachedMock.mockImplementation(handleGetPressPublishers);

    render(<SentimentView mode="sentiment" scope="press" />);

    expect(await screen.findByText("Sentimiento en Prensa")).toBeInTheDocument();
    await waitFor(() => {
      const publishersBlock = screen.getByText("MEDIOS EN PRENSA").parentElement;
      expect(publishersBlock).toBeTruthy();
      expect(within(publishersBlock as HTMLElement).getByText("eleconomista.es")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("Downdetector")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("News (1)")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("Downdetector (1)")).toBeInTheDocument();
    });
  });

  it("aligns press publishers with selected source filters in press scope", async () => {
    const metaPressResponse = {
      ...metaResponse,
      sources_enabled: ["news", "downdetector", "trustpilot"],
      sources_available: ["news", "downdetector", "trustpilot"],
    };
    const itemsPressResponse = {
      ...itemsResponse,
      sources_enabled: ["news", "downdetector", "trustpilot"],
      items: [
        {
          id: "press-news-2",
          source: "news",
          geo: "España",
          actor: "Acme Bank",
          title: "BBVA mejora métricas - eleconomista.es",
          text: '<font color="#6f6f6f">eleconomista.es</font>',
          sentiment: "positive",
          published_at: "2025-01-01T10:00:00Z",
          signals: { source: "Google News" },
          url: "https://news.google.com/rss/articles/def?oc=5",
        },
        {
          id: "press-dd-2",
          source: "downdetector",
          geo: "España",
          actor: "Acme Bank",
          title: "Incidencias en banca móvil",
          text: "Pico de incidencias",
          sentiment: "negative",
          published_at: "2025-01-02T10:00:00Z",
          signals: {
            publisher_name: "Downdetector",
            publisher_domain: "downdetector.es",
          },
          url: "https://downdetector.es",
        },
        {
          id: "press-tp-1",
          source: "trustpilot",
          geo: "España",
          actor: "Acme Bank",
          title: "Opinión en Trustpilot",
          text: "Valoración",
          sentiment: "neutral",
          published_at: "2025-01-03T10:00:00Z",
          signals: {
            publisher_name: "Trustpilot",
            publisher_domain: "trustpilot.com",
          },
          url: "https://www.trustpilot.com",
        },
      ],
      stats: { count: 3 },
    };

    const handleGetPressFilter = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(metaPressResponse);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(itemsPressResponse);
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({ items: [] });
    };

    apiGetMock.mockImplementation(handleGetPressFilter);
    apiGetCachedMock.mockImplementation(handleGetPressFilter);

    render(<SentimentView mode="sentiment" scope="press" />);

    expect(await screen.findByText("Sentimiento en Prensa")).toBeInTheDocument();
    await waitFor(() => {
      const publishersBlock = screen.getByText("MEDIOS EN PRENSA").parentElement;
      expect(publishersBlock).toBeTruthy();
      expect(within(publishersBlock as HTMLElement).getByText("eleconomista.es")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("Downdetector")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("Trustpilot")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("News (1)")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("Downdetector (1)")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("Trustpilot (1)")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /^news/i }));

    await waitFor(() => {
      const publishersBlock = screen.getByText("MEDIOS EN PRENSA").parentElement;
      expect(publishersBlock).toBeTruthy();
      expect(within(publishersBlock as HTMLElement).getByText("eleconomista.es")).toBeInTheDocument();
      expect(
        within(publishersBlock as HTMLElement).queryByText("Downdetector")
      ).not.toBeInTheDocument();
      expect(
        within(publishersBlock as HTMLElement).queryByText("Trustpilot")
      ).not.toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("News (1)")).toBeInTheDocument();
      expect(
        within(publishersBlock as HTMLElement).queryByText("Downdetector (1)")
      ).not.toBeInTheDocument();
      expect(
        within(publishersBlock as HTMLElement).queryByText("Trustpilot (1)")
      ).not.toBeInTheDocument();
    });
  });

  it("refreshes reputation meta bypassing cache after settings change", async () => {
    render(<SentimientoPage />);

    await screen.findByLabelText("País");

    await waitFor(() => {
      expect(apiGetCachedMock).toHaveBeenCalledWith(
        "/reputation/meta",
        expect.objectContaining({ ttlMs: 60000, force: false })
      );
    });

    window.dispatchEvent(
      new CustomEvent(SETTINGS_CHANGED_EVENT, { detail: { updated_at: "2026-02-13T12:00:00Z" } })
    );

    await waitFor(() => {
      const hasForcedMetaRefresh = apiGetCachedMock.mock.calls.some(
        ([path, options]) =>
          path === "/reputation/meta" &&
          typeof options === "object" &&
          options !== null &&
          "force" in options &&
          options.force === true
      );
      expect(hasForcedMetaRefresh).toBe(true);
    });
  });

  it("shows source counters as principal vs others when comparisons are enabled", async () => {
    render(<SentimentView mode="sentiment" scope="all" />);

    await screen.findByLabelText("País");

    await waitFor(() => {
      const newsChip = screen.getByRole("button", { name: /news/i });
      expect(newsChip).toHaveTextContent(/1\s*vs\s*1/);
      expect(screen.queryByText("TOP FUENTES")).not.toBeInTheDocument();

      const actorsBlock = screen.getByText("ACTORES DEL MERCADO").parentElement;
      expect(actorsBlock).toBeTruthy();
      expect(within(actorsBlock as HTMLElement).getByText("App Store (1)")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Google Play (1)")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Acme Bank")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Beta Bank")).toBeInTheDocument();
    });
  });

  it("shows source counters as principal-only when comparisons are disabled", async () => {
    const metaNoComparisons = { ...metaResponse, ui_show_comparisons: false };
    const handleGetNoComparisons = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(metaNoComparisons);
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
    apiGetMock.mockImplementation(handleGetNoComparisons);
    apiGetCachedMock.mockImplementation(handleGetNoComparisons);

    render(<SentimentView mode="sentiment" scope="all" />);

    await screen.findByLabelText("País");

    await waitFor(() => {
      const newsChip = screen.getByRole("button", { name: /news/i });
      expect(within(newsChip).getByText("1")).toBeInTheDocument();
      expect(within(newsChip).queryByText(/vs/i)).not.toBeInTheDocument();
      const totalCard = screen.getByText("Total menciones").parentElement;
      expect(totalCard).toBeTruthy();
      expect(
        within(totalCard as HTMLElement).getByText((value) => value.trim() === "2"),
      ).toBeInTheDocument();
      expect(within(totalCard as HTMLElement).queryByText(/vs/i)).not.toBeInTheDocument();
      expect(screen.queryByText("TOP FUENTES")).not.toBeInTheDocument();
      const actorsBlock = screen.getByText("ACTORES DEL MERCADO").parentElement;
      expect(actorsBlock).toBeTruthy();
      expect(within(actorsBlock as HTMLElement).getByText("Acme Bank")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).queryByText("Beta Bank")).not.toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("App Store (1)")).toBeInTheDocument();
      expect(within(actorsBlock as HTMLElement).getByText("Google Play (0)")).toBeInTheDocument();
    });
  });

  it("keeps press publishers aligned with principal context when comparisons are disabled", async () => {
    const metaNoComparisonsPress = {
      ...metaResponse,
      ui_show_comparisons: false,
      sources_enabled: ["news", "trustpilot"],
      sources_available: ["news", "trustpilot"],
    };
    const itemsNoComparisonsPress = {
      ...itemsResponse,
      sources_enabled: ["news", "trustpilot"],
      items: [
        {
          id: "principal-news-press",
          source: "news",
          geo: "España",
          actor: "Acme Bank",
          title: "Acme en portada - democrata.es",
          text: '<font color="#6f6f6f">democrata.es</font>',
          sentiment: "positive",
          published_at: "2025-01-01T10:00:00Z",
          signals: { source: "Google News" },
          url: "https://news.google.com/rss/articles/ghi?oc=5",
        },
        {
          id: "other-trustpilot-press",
          source: "trustpilot",
          geo: "España",
          actor: "Beta Bank",
          title: "Opinión externa",
          text: "Reseña de otro actor",
          sentiment: "negative",
          published_at: "2025-01-02T10:00:00Z",
          signals: { publisher_name: "Trustpilot", publisher_domain: "trustpilot.com" },
          url: "https://www.trustpilot.com",
        },
      ],
      stats: { count: 2 },
    };

    const handleGetNoComparisonsPress = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(metaNoComparisonsPress);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(itemsNoComparisonsPress);
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
      }
      return Promise.resolve({ items: [] });
    };

    apiGetMock.mockImplementation(handleGetNoComparisonsPress);
    apiGetCachedMock.mockImplementation(handleGetNoComparisonsPress);

    render(<SentimentView mode="sentiment" scope="press" />);

    expect(await screen.findByText("Sentimiento en Prensa")).toBeInTheDocument();
    await waitFor(() => {
      const publishersBlock = screen.getByText("MEDIOS EN PRENSA").parentElement;
      expect(publishersBlock).toBeTruthy();
      expect(within(publishersBlock as HTMLElement).getByText("democrata.es")).toBeInTheDocument();
      expect(within(publishersBlock as HTMLElement).getByText("News (1)")).toBeInTheDocument();
      expect(
        within(publishersBlock as HTMLElement).queryByText("Trustpilot")
      ).not.toBeInTheDocument();
      expect(
        within(publishersBlock as HTMLElement).queryByText("Trustpilot (1)")
      ).not.toBeInTheDocument();
    });
  });

  it("defaults sentiment filters to current month and Spain when available", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2025-01-15T12:00:00Z"));
    try {
      render(<SentimentView mode="sentiment" scope="all" />);

      const geoSelect = (await screen.findByLabelText("País")) as HTMLSelectElement;
      await waitFor(() => {
        expect(geoSelect.value).toBe("España");
      });

      const fromInput = screen.getByLabelText("Desde") as HTMLInputElement;
      const toInput = screen.getByLabelText("Hasta") as HTMLInputElement;
      const now = new Date();
      const yyyy = String(now.getFullYear());
      const mm = String(now.getMonth() + 1).padStart(2, "0");
      const dd = String(now.getDate()).padStart(2, "0");
      const expectedFrom = `${yyyy}-${mm}-01`;
      const expectedTo = `${yyyy}-${mm}-${dd}`;
      expect(fromInput.value).toBe(expectedFrom);
      expect(toInput.value).toBe(expectedTo);

      const listedHeader = screen.getByText("LISTADO");
      const listedContainer = listedHeader.parentElement;
      expect(listedContainer).toBeTruthy();
      expect(
        within(listedContainer as HTMLElement).queryByText("LISTADO COMPLETO")
      ).not.toBeInTheDocument();
      expect(
        within(listedContainer as HTMLElement).getByText(
          /SENTIMIENTO:\s*Todos\s*·\s*PAÍS:\s*España/i
        )
      ).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders Google Play stars when rating is provided as score", async () => {
    const metaScoreResponse = {
      ...metaResponse,
      sources_enabled: ["google_play"],
      sources_available: ["google_play"],
    };
    const itemsScoreResponse = {
      ...itemsResponse,
      sources_enabled: ["google_play"],
      items: [
        {
          id: "gp-score-1",
          source: "google_play",
          geo: "España",
          actor: "Acme, Bank",
          title: "Google Play crítica",
          text: "La app falla en login",
          sentiment: "negative",
          published_at: "2026-02-13T10:00:00Z",
          signals: { score: "1" },
        },
      ],
      stats: { count: 1 },
    };
    const handleGetScore = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(metaScoreResponse);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(itemsScoreResponse);
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
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
            unanswered_positive: 0,
            unanswered_neutral: 0,
            unanswered_negative: 1,
          },
          actor_breakdown: [],
          repeated_replies: [],
          answered_items: [],
        });
      }
      return Promise.resolve({ items: [] });
    };
    apiGetMock.mockImplementation(handleGetScore);
    apiGetCachedMock.mockImplementation(handleGetScore);

    render(<SentimentView mode="sentiment" scope="all" />);

    const mentionTitle = await screen.findByText("Google Play crítica");
    const mentionCard = mentionTitle.closest("article");
    expect(mentionCard).toBeTruthy();
    expect(within(mentionCard as HTMLElement).getByText("1.0")).toBeInTheDocument();
    expect(within(mentionCard as HTMLElement).getByText("/5")).toBeInTheDocument();
  });

  it("renders Google Play stars when rating is nested in reviewRating", async () => {
    const metaNestedResponse = {
      ...metaResponse,
      sources_enabled: ["google_play"],
      sources_available: ["google_play"],
    };
    const itemsNestedResponse = {
      ...itemsResponse,
      sources_enabled: ["google_play"],
      items: [
        {
          id: "gp-nested-1",
          source: "google_play",
          geo: "España",
          actor: "Acme, Bank",
          author: "Cliente GP",
          title: "Google Play crítica nested",
          text: "La app falla en login",
          sentiment: "negative",
          published_at: "2026-02-13T10:00:00Z",
          signals: { reviewRating: { value: "1" } },
        },
      ],
      stats: { count: 1 },
    };
    const handleGetNested = (path: string) => {
      if (path.startsWith("/reputation/meta")) {
        return Promise.resolve(metaNestedResponse);
      }
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve(profilesResponse);
      }
      if (path.startsWith("/reputation/items")) {
        return Promise.resolve(itemsNestedResponse);
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve({ groups: [], advanced_options: [] });
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
            unanswered_positive: 0,
            unanswered_neutral: 0,
            unanswered_negative: 1,
          },
          actor_breakdown: [],
          repeated_replies: [],
          answered_items: [],
        });
      }
      return Promise.resolve({ items: [] });
    };
    apiGetMock.mockImplementation(handleGetNested);
    apiGetCachedMock.mockImplementation(handleGetNested);

    render(<SentimentView mode="sentiment" scope="all" />);

    const mentionTitle = await screen.findByText("Google Play crítica nested");
    const mentionCard = mentionTitle.closest("article");
    expect(mentionCard).toBeTruthy();
    expect(within(mentionCard as HTMLElement).getByText("1.0")).toBeInTheDocument();
    expect(within(mentionCard as HTMLElement).getByText("/5")).toBeInTheDocument();
    expect(within(mentionCard as HTMLElement).getByText("Cliente GP")).toBeInTheDocument();
  });
});
