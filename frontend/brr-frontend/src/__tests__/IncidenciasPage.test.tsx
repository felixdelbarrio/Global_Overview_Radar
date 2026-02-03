/** Tests de la vista de incidencias. */

import React from "react";
import { render, screen } from "@testing-library/react";
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

import { apiGet } from "@/lib/api";
import IncidenciasPage from "@/app/incidencias/page";

const apiGetMock = vi.mocked(apiGet);

it("filters incidents by search and severity", async () => {
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
          opened_at: "2025-01-10",
          product: "Mobile",
          feature: "Login",
        },
        {
          global_id: "INC-2",
          title: "Pago lento",
          status: "CLOSED",
          severity: "LOW",
          opened_at: "2025-01-08",
          product: "Payments",
          feature: "Transfer",
        },
      ],
    });
  });

  render(<IncidenciasPage />);

  expect(await screen.findByText("INC-1")).toBeInTheDocument();
  expect(screen.getByText("EVOLUCIÓN TEMPORAL")).toBeInTheDocument();
  expect(screen.getByText("INC-2")).toBeInTheDocument();

  const search = screen.getByPlaceholderText("ID, título, producto, funcionalidad…");
  await userEvent.type(search, "login");
  expect(screen.getByText("INC-1")).toBeInTheDocument();
  expect(screen.queryByText("INC-2")).not.toBeInTheDocument();

  await userEvent.clear(search);
  const severity = screen.getByDisplayValue("Todas");
  await userEvent.selectOptions(severity, "LOW");
  expect(screen.getByText("INC-2")).toBeInTheDocument();
  expect(screen.queryByText("INC-1")).not.toBeInTheDocument();

  await userEvent.type(search, "no-match");
  expect(
    screen.getByText("No hay incidencias para mostrar con los filtros actuales.")
  ).toBeInTheDocument();
});
