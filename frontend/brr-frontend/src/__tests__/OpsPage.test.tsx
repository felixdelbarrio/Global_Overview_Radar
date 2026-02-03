/** Tests de la vista Ops Executive. */

import React from "react";
import { render, screen, within } from "@testing-library/react";
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
  usePathname: () => "/ops",
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet } from "@/lib/api";
import OpsPage from "@/app/ops/page";

const apiGetMock = vi.mocked(apiGet);

function makeItems(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    global_id: `INC-${i + 1}`,
    title: `Incident ${i + 1}`,
    status: i % 2 === 0 ? "OPEN" : "CLOSED",
    severity: i % 3 === 0 ? "CRITICAL" : "LOW",
    opened_at: `2025-01-${(i + 1).toString().padStart(2, "0")}`,
    clients_affected: 3,
    product: "App",
    feature: "Login",
  }));
}

it("renders KPIs, supports filtering and pagination", async () => {
  apiGetMock.mockImplementation((path: string) => {
    if (path.startsWith("/kpis")) {
      return Promise.resolve({
        open_total: 9,
        open_by_severity: { CRITICAL: 2, HIGH: 0, MEDIUM: 0, LOW: 7, UNKNOWN: 0 },
        new_total: 0,
        new_by_severity: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, UNKNOWN: 0 },
        new_masters: 0,
        closed_total: 0,
        closed_by_severity: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, UNKNOWN: 0 },
        mean_resolution_days_overall: null,
        mean_resolution_days_by_severity: {},
        open_over_threshold_pct: 0,
        open_over_threshold_list: ["INC-1"],
      });
    }
    return Promise.resolve({ items: makeItems(9) });
  });

  render(<OpsPage />);

  expect(await screen.findByText("INC-1")).toBeInTheDocument();
  expect(screen.getAllByText(/Open:\s*9/i).length).toBeGreaterThan(0);

  const pageIndicator = await screen.findByText("1 / 2");
  const pager = pageIndicator.parentElement?.parentElement;
  const pagerButtons = pager?.querySelectorAll("button");
  if (pagerButtons && pagerButtons.length > 1) {
    await userEvent.click(pagerButtons[1]);
  }
  expect(screen.getByText("2 / 2")).toBeInTheDocument();

  const criticalBtn = screen.getByRole("button", { name: "Critical" });
  await userEvent.click(criticalBtn);
  const table = screen.getByRole("table");
  expect(within(table).getByText("INC-1")).toBeInTheDocument();
});

it("supports header sorting and missing filter", async () => {
  apiGetMock.mockImplementation((path: string) => {
    if (path.startsWith("/kpis")) {
      return Promise.resolve({
        open_total: 2,
        open_by_severity: { CRITICAL: 1, HIGH: 0, MEDIUM: 0, LOW: 1, UNKNOWN: 0 },
        new_total: 0,
        new_by_severity: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, UNKNOWN: 0 },
        new_masters: 0,
        closed_total: 0,
        closed_by_severity: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, UNKNOWN: 0 },
        mean_resolution_days_overall: null,
        mean_resolution_days_by_severity: {},
        open_over_threshold_pct: 0,
        open_over_threshold_list: [],
      });
    }
    return Promise.resolve({
      items: [
        {
          global_id: "INC-2",
          title: "Incident 2",
          status: "OPEN",
          severity: "LOW",
          opened_at: "2025-01-02",
          clients_affected: 10,
          product: "App",
          feature: "Login",
          missing_in_last_ingest: true,
        },
        {
          global_id: "INC-1",
          title: "Incident 1",
          status: "CLOSED",
          severity: "CRITICAL",
          opened_at: "2025-01-03",
          clients_affected: 1,
          product: "App",
          feature: "Login",
          missing_in_last_ingest: false,
        },
      ],
    });
  });

  render(<OpsPage />);

  const table = await screen.findByRole("table");
  const clientesHeader = screen.getByRole("button", { name: /Clientes/i });
  await userEvent.click(clientesHeader);
  const rowsAfterDesc = within(table).getAllByRole("row");
  expect(within(rowsAfterDesc[1]).getByText("INC-2")).toBeInTheDocument();
  await userEvent.click(clientesHeader);
  const rowsAfterAsc = within(table).getAllByRole("row");
  expect(within(rowsAfterAsc[1]).getByText("INC-1")).toBeInTheDocument();

  const missingFilter = screen.getByRole("button", { name: /Desaparecidas/i });
  await userEvent.click(missingFilter);
  expect(within(table).getByText("INC-2")).toBeInTheDocument();
  expect(within(table).queryByText("INC-1")).not.toBeInTheDocument();
});
