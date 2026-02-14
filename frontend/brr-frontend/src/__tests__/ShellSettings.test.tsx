/** Tests del panel de Shell (ingestas y configuracion). */

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
  usePathname: () => "/",
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiGetCached: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiGetCached, apiPost } from "@/lib/api";
import { Shell } from "@/components/Shell";

const apiGetMock = vi.mocked(apiGet);
const apiGetCachedMock = vi.mocked(apiGetCached);
const apiPostMock = vi.mocked(apiPost);

const settingsResponse = {
  groups: [
    {
      id: "sources_public",
      label: "Fuentes",
      fields: [
        {
          key: "sources.news",
          label: "Noticias",
          description: "RSS",
          type: "boolean",
          value: true,
        },
      ],
    },
    {
      id: "sources_credentials",
      label: "Credenciales",
      fields: [
        {
          key: "sources.newsapi",
          label: "NewsAPI",
          description: "Provider",
          type: "boolean",
          value: false,
        },
        {
          key: "keys.newsapi",
          label: "NewsAPI Key",
          description: "API key",
          type: "secret",
          value: "********",
          configured: true,
        },
      ],
    },
  ],
  updated_at: "2025-01-01T00:00:00Z",
  advanced_options: [],
};

const settingsWithCredentialNewsAndLlm = {
  groups: [
    {
      id: "sources_press",
      label: "Fuentes Prensa OPEN",
      fields: [
        {
          key: "sources.news",
          label: "Noticias (RSS)",
          description: "Agregadores y RSS.",
          type: "boolean",
          value: false,
        },
      ],
    },
    {
      id: "sources_credentials",
      label: "Credenciales",
      fields: [
        {
          key: "sources.newsapi",
          label: "NewsAPI",
          description: "Provider",
          type: "boolean",
          value: false,
        },
        {
          key: "keys.newsapi",
          label: "NewsAPI Key",
          description: "API key",
          type: "secret",
          value: "",
          configured: false,
        },
        {
          key: "keys.news",
          label: "API Key News (opcional)",
          description: "Clave News",
          type: "secret",
          value: "",
          configured: false,
        },
      ],
    },
    {
      id: "llm",
      label: "IA (LLM)",
      fields: [
        {
          key: "llm.enabled",
          label: "IA activa",
          description: "Activa la clasificación con IA.",
          type: "boolean",
          value: true,
        },
        {
          key: "llm.provider",
          label: "Proveedor",
          description: "Proveedor de IA principal.",
          type: "select",
          value: "openai",
          options: ["openai", "gemini"],
        },
        {
          key: "llm.openai_key",
          label: "OpenAI API Key",
          description: "Clave OpenAI",
          type: "secret",
          value: "********",
          configured: true,
        },
        {
          key: "llm.gemini_key",
          label: "Gemini API Key",
          description: "Clave Gemini",
          type: "secret",
          value: "",
          configured: false,
        },
      ],
    },
    {
      id: "news",
      label: "Noticias",
      fields: [
        {
          key: "keys.news",
          label: "API Key News (opcional)",
          description: "Clave News",
          type: "secret",
          value: "",
          configured: false,
        },
      ],
    },
  ],
  updated_at: "2025-01-01T00:00:00Z",
  advanced_options: [],
};

describe("Shell settings and ingest", () => {
  beforeEach(() => {
    const handleGet = (path: string) => {
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve({
          active: { source: "default", profiles: ["banking"], profile_key: "banking" },
          options: { default: ["banking"], samples: ["banking"] },
        });
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve(settingsResponse);
      }
      return Promise.resolve({});
    };
    apiGetMock.mockImplementation(handleGet);
    apiGetCachedMock.mockImplementation(handleGet);

    apiPostMock.mockImplementation((path: string) => {
      if (path === "/ingest/reputation") {
        return Promise.resolve({
          id: "job-1",
          kind: "reputation",
          status: "queued",
          progress: 10,
        });
      }
      if (path === "/reputation/settings") {
        return Promise.resolve(settingsResponse);
      }
      if (path === "/reputation/profiles") {
        return Promise.resolve({
          active: { source: "samples", profiles: ["banking"], profile_key: "banking" },
          auto_ingest: { started: false },
        });
      }
      return Promise.resolve({});
    });
  });

  it("opens settings and ingest panels", async () => {
    render(
      <Shell>
        <div>Contenido</div>
      </Shell>
    );

    expect((await screen.findAllByRole("link", { name: "Dashboard" })).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByLabelText("Configuración"));
    expect(await screen.findByText("CONFIGURACIÓN")).toBeInTheDocument();
    const newsLabels = await screen.findAllByText("Noticias");
    expect(newsLabels.length).toBeGreaterThan(0);

    const newsLabel = newsLabels[0];
    const newsToggle =
      newsLabel.parentElement?.parentElement?.querySelector("button");
    expect(newsToggle).toBeTruthy();
    fireEvent.click(newsToggle as HTMLButtonElement);
    fireEvent.click(screen.getByText("RESET"));
    fireEvent.click(screen.getByText("Guardar"));

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        "/reputation/settings",
        expect.objectContaining({
          values: expect.objectContaining({
            "keys.newsapi": "",
          }),
        })
      );
    });

    fireEvent.click(screen.getByLabelText("Centro de ingestas"));
    expect(await screen.findByText("CENTRO DE INGESTA")).toBeInTheDocument();

    const startButtons = screen.getAllByText("Iniciar ingesta");
    fireEvent.click(startButtons[0]);

    await waitFor(() => {
      expect(screen.queryByText("CENTRO DE INGESTA")).not.toBeInTheDocument();
    });

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith("/ingest/reputation", {
        force: false,
        all_sources: false,
      });
    });

    fireEvent.click(screen.getByLabelText(/Cambiar a modo (oscuro|claro)/));
  });

  it("allows enabling RSS news without API key in credential section", async () => {
    const handleGet = (path: string) => {
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve({
          active: { source: "default", profiles: ["banking"], profile_key: "banking" },
          options: { default: ["banking"], samples: ["banking"] },
        });
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve(settingsWithCredentialNewsAndLlm);
      }
      return Promise.resolve({});
    };
    apiGetMock.mockImplementation(handleGet);
    apiGetCachedMock.mockImplementation(handleGet);
    apiPostMock.mockImplementation((path: string) => {
      if (path === "/reputation/settings") {
        return Promise.resolve(settingsWithCredentialNewsAndLlm);
      }
      return Promise.resolve({});
    });

    render(
      <Shell>
        <div>Contenido</div>
      </Shell>
    );

    fireEvent.click(screen.getByLabelText("Configuración"));
    expect(await screen.findByText("CONFIGURACIÓN")).toBeInTheDocument();

    const newsCredentialToggle = await screen.findByRole("button", {
      name: /Activar\s+Noticias/i,
    });
    fireEvent.click(newsCredentialToggle);
    fireEvent.click(screen.getByText("Guardar"));

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        "/reputation/settings",
        expect.objectContaining({
          values: expect.objectContaining({
            "sources.news": true,
          }),
        })
      );
    });
  });

  it("shows one LLM key input and disables IA toggle when selected provider has no key", async () => {
    const handleGet = (path: string) => {
      if (path.startsWith("/reputation/profiles")) {
        return Promise.resolve({
          active: { source: "default", profiles: ["banking"], profile_key: "banking" },
          options: { default: ["banking"], samples: ["banking"] },
        });
      }
      if (path.startsWith("/reputation/settings")) {
        return Promise.resolve(settingsWithCredentialNewsAndLlm);
      }
      return Promise.resolve({});
    };
    apiGetMock.mockImplementation(handleGet);
    apiGetCachedMock.mockImplementation(handleGet);
    apiPostMock.mockImplementation((path: string) => {
      if (path === "/reputation/settings") {
        return Promise.resolve(settingsWithCredentialNewsAndLlm);
      }
      return Promise.resolve({});
    });

    render(
      <Shell>
        <div>Contenido</div>
      </Shell>
    );

    fireEvent.click(screen.getByLabelText("Configuración"));
    expect(await screen.findByText("CONFIGURACIÓN")).toBeInTheDocument();

    expect(screen.getByText("OpenAI API Key")).toBeInTheDocument();
    expect(screen.queryByText("Gemini API Key")).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("API Key IA")).toHaveLength(1);

    fireEvent.change(screen.getByLabelText("Proveedor IA"), {
      target: { value: "gemini" },
    });

    await waitFor(() => {
      expect(screen.getByText("Gemini API Key")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Activar IA (LLM)")).toBeDisabled();

    fireEvent.click(screen.getByText("Guardar"));

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        "/reputation/settings",
        expect.objectContaining({
          values: expect.objectContaining({
            "llm.provider": "gemini",
            "llm.enabled": false,
          }),
        })
      );
    });
  });
});
