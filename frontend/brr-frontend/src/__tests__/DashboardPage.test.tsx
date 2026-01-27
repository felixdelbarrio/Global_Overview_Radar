/** Tests del dashboard ejecutivo. */

import React from "react";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

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

vi.mock("next/dynamic", () => ({
  default: () => () => <div data-testid="evolution-chart" />,
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
}));

import { apiGet } from "@/lib/api";
import DashboardPage from "@/app/page";

const apiGetMock = vi.mocked(apiGet);

it("renders KPI values and chart", async () => {
  apiGetMock.mockImplementation((path: string) => {
    if (path.startsWith("/kpis")) {
      return Promise.resolve({
        open_total: 10,
        open_by_severity: {
          CRITICAL: 1,
          HIGH: 2,
          MEDIUM: 3,
          LOW: 4,
          UNKNOWN: 0,
        },
        new_total: 2,
        new_by_severity: {
          CRITICAL: 0,
          HIGH: 1,
          MEDIUM: 1,
          LOW: 0,
          UNKNOWN: 0,
        },
        new_masters: 1,
        closed_total: 1,
        closed_by_severity: {
          CRITICAL: 0,
          HIGH: 0,
          MEDIUM: 1,
          LOW: 0,
          UNKNOWN: 0,
        },
        mean_resolution_days_overall: 3,
        mean_resolution_days_by_severity: { HIGH: 3 },
        open_over_threshold_pct: 12.3,
        open_over_threshold_list: ["src:1"],
      });
    }

    return Promise.resolve({
      days: 60,
      series: [{ date: "2025-01-01", open: 1, new: 1, closed: 0 }],
    });
  });

  render(<DashboardPage />);

  expect(await screen.findByText("10")).toBeInTheDocument();
  expect(screen.getByText("12.3%")).toBeInTheDocument();
  expect(screen.getByTestId("evolution-chart")).toBeInTheDocument();
});
