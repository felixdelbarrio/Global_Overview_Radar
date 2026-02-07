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
    expect(await screen.findByText("Noticias")).toBeInTheDocument();

    const newsLabel = screen.getByText("Noticias");
    const newsToggle =
      newsLabel.parentElement?.parentElement?.querySelector("button");
    expect(newsToggle).toBeTruthy();
    fireEvent.click(newsToggle as HTMLButtonElement);
    fireEvent.click(screen.getByText("Guardar"));

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        "/reputation/settings",
        expect.anything()
      );
    });

    fireEvent.click(screen.getByLabelText("Centro de ingestas"));
    expect(await screen.findByText("CENTRO DE INGESTA")).toBeInTheDocument();

    const startButtons = screen.getAllByText("Iniciar ingesta");
    fireEvent.click(startButtons[0]);

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith("/ingest/reputation", {
        force: false,
        all_sources: false,
      });
    });

    fireEvent.click(screen.getByLabelText(/Cambiar a modo (oscuro|claro)/));
  });
});
