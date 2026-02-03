/** Tests de la vista de incidencias. */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/incidencias",
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet, apiPost } from "@/lib/api";
import IncidenciasPage from "@/app/incidencias/page";

const apiGetMock = vi.mocked(apiGet);
const apiPostMock = vi.mocked(apiPost);

it("filters incidents by search and severity", async () => {
  const today = new Date();
  const openedRecent = new Date(today);
  openedRecent.setDate(today.getDate() - 10);
  const openedOlder = new Date(today);
  openedOlder.setDate(today.getDate() - 12);
  const openedRecentStr = openedRecent.toISOString().slice(0, 10);
  const openedOlderStr = openedOlder.toISOString().slice(0, 10);
  apiPostMock.mockResolvedValue({ updated: 1 });
  apiGetMock.mockImplementation((path: string) => {
    if (path.startsWith("/evolution")) {
      return Promise.resolve({
        days: 90,
        series: [{ date: "2025-01-01", open: 1, new: 1, closed: 0 }],
      });
    }
    return Promise.resolve({
      items: [
        {
          global_id: "INC-1",
          title: "Login error",
          status: "OPEN",
          severity: "HIGH",
          opened_at: openedRecentStr,
          product: "Mobile",
          feature: "Login",
          missing_in_last_ingest: true,
        },
        {
          global_id: "INC-2",
          title: "Pago lento",
          status: "CLOSED",
          severity: "LOW",
          opened_at: openedOlderStr,
          product: "Payments",
          feature: "Transfer",
          missing_in_last_ingest: false,
        },
      ],
      generated_at: openedRecentStr,
    });
  });

  const user = userEvent.setup();
  render(<IncidenciasPage />);

  expect(await screen.findByText("INC-1")).toBeInTheDocument();
  expect(screen.getByText("EVOLUCIÓN TEMPORAL")).toBeInTheDocument();
  expect(screen.getByText("INC-2")).toBeInTheDocument();

  const search = screen.getByPlaceholderText("ID, título, producto, funcionalidad…");
  await user.type(search, "login");
  expect(screen.getByText("INC-1")).toBeInTheDocument();
  expect(screen.queryByText("INC-2")).not.toBeInTheDocument();

  await user.clear(search);
  const severity = screen.getByDisplayValue("Todas");
  await user.selectOptions(severity, "LOW");
  expect(screen.getByText("INC-2")).toBeInTheDocument();
  expect(screen.queryByText("INC-1")).not.toBeInTheDocument();

  await user.type(search, "no-match");
  expect(
    screen.getByText("No hay incidencias para mostrar con los filtros actuales.")
  ).toBeInTheDocument();
  await user.clear(search);
  await user.selectOptions(severity, "ALL");

  const missingFilter = screen.getByRole("button", { name: /Desaparecidas/i });
  await user.click(missingFilter);
  expect(screen.getByText("INC-1")).toBeInTheDocument();
  expect(screen.queryByText("INC-2")).not.toBeInTheDocument();

  const editButtons = screen.getAllByRole("button", { name: "Editar" });
  await user.click(editButtons[0]);
  const statusSelect = screen.getByDisplayValue("OPEN");
  await user.selectOptions(statusSelect, "CLOSED");
  const severitySelect = screen.getByDisplayValue("HIGH");
  await user.selectOptions(severitySelect, "LOW");
  const noteInput = screen.getByPlaceholderText("Motivo o seguimiento");
  await user.type(noteInput, "Cerrada manualmente");
  await user.click(screen.getByRole("button", { name: "Guardar" }));
  await waitFor(() =>
    expect(apiPostMock).toHaveBeenCalledWith("/incidents/override", {
      ids: ["INC-1"],
      status: "CLOSED",
      severity: "LOW",
      note: "Cerrada manualmente",
    })
  );
});
