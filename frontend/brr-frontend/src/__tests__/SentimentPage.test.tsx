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

    const responsesHeading = await screen.findByText("Opiniones contestadas");
    const responsesCard = responsesHeading.parentElement;
    expect(responsesCard).toBeTruthy();
    expect(within(responsesCard as HTMLElement).getByText("Neutras")).toBeInTheDocument();
    const totalCard = within(responsesCard as HTMLElement).getByText("Total").parentElement;
    expect(totalCard).toBeTruthy();
    expect(totalCard as HTMLElement).toHaveTextContent(/2/);
    expect(totalCard as HTMLElement).toHaveTextContent(/3/);
    expect(totalCard as HTMLElement).toHaveTextContent(/vs/i);
    expect(within(responsesCard as HTMLElement).getByText("Neutra principal")).toBeInTheDocument();
    expect(within(responsesCard as HTMLElement).getByText("Neutra beta 1")).toBeInTheDocument();
    expect(within(responsesCard as HTMLElement).getByText("Neutra beta 2")).toBeInTheDocument();

    await waitFor(() => {
      const summaryCalls = apiGetMock.mock.calls.filter(
        ([path]) =>
          typeof path === "string" && path.startsWith("/reputation/responses/summary?"),
      );
      expect(summaryCalls.length).toBeGreaterThan(0);
      const allCallsHaveRange = summaryCalls.every(
        ([path]) => typeof path === "string" && path.includes("from_date=") && path.includes("to_date="),
      );
      const hasGeoFilter = summaryCalls.some(
        ([path]) => typeof path === "string" && path.includes("geo=Espa%C3%B1a"),
      );
      expect(allCallsHaveRange).toBe(true);
      expect(hasGeoFilter).toBe(true);
    });

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
      const comparisonCells = screen
        .getAllByRole("cell")
        .filter((cell) => /2\s*vs\s*2/.test(cell.textContent || ""));
      expect(comparisonCells.length).toBeGreaterThanOrEqual(1);
      const geoTitle = Array.from(document.querySelectorAll("div")).find((element) =>
        (element.textContent || "").trim().startsWith("SENTIMIENTO POR PAÍS:"),
      );
      expect(geoTitle).toBeTruthy();
      expect(geoTitle?.textContent || "").toMatch(/vs/i);
      const geoCell = screen.getByText("España", { selector: "td" });
      const geoRow = geoCell.closest("tr");
      expect(geoRow).toBeTruthy();
      const mentionsCell = within(geoRow as HTMLElement).getAllByRole("cell")[1];
      expect(mentionsCell).toHaveTextContent(/2\s*vs\s*2/);

      const topSourcesBlock = screen.getByText("TOP FUENTES").parentElement;
      expect(topSourcesBlock).toBeTruthy();
      const newsRowLabel = within(topSourcesBlock as HTMLElement).getByText("news");
      const newsRow = newsRowLabel.parentElement;
      expect(newsRow).toBeTruthy();
      expect(within(newsRow as HTMLElement).getByText("2")).toBeInTheDocument();
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
      const geoTitle = Array.from(document.querySelectorAll("div")).find((element) =>
        (element.textContent || "").trim().startsWith("SENTIMIENTO POR PAÍS:"),
      );
      expect(geoTitle).toBeTruthy();
      expect(geoTitle?.textContent || "").not.toMatch(/vs/i);
      const totalCard = screen.getByText("Total menciones").parentElement;
      expect(totalCard).toBeTruthy();
      expect(
        within(totalCard as HTMLElement).getByText((value) => value.trim() === "2"),
      ).toBeInTheDocument();
      expect(within(totalCard as HTMLElement).queryByText(/vs/i)).not.toBeInTheDocument();

      const topSourcesBlock = screen.getByText("TOP FUENTES").parentElement;
      expect(topSourcesBlock).toBeTruthy();
      const newsRowLabel = within(topSourcesBlock as HTMLElement).getByText("news");
      const newsRow = newsRowLabel.parentElement;
      expect(newsRow).toBeTruthy();
      expect(within(newsRow as HTMLElement).getByText("1")).toBeInTheDocument();
    });
  });

  it("defaults sentiment filters to current month and Spain when available", async () => {
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
    expect(within(listedContainer as HTMLElement).queryByText("LISTADO COMPLETO")).not.toBeInTheDocument();
    expect(
      within(listedContainer as HTMLElement).getByText(
        /SENTIMIENTO:\s*Todos\s*·\s*PAÍS:\s*España/i
      )
    ).toBeInTheDocument();
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
});
