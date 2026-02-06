/** Tests del componente Shell (layout y navegacion). */

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
  usePathname: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { usePathname } from "next/navigation";
import { apiGet } from "@/lib/api";
import { Shell } from "@/components/Shell";

const usePathnameMock = vi.mocked(usePathname);
const apiGetMock = vi.mocked(apiGet);

describe("Shell", () => {
  beforeEach(() => {
    usePathnameMock.mockReturnValue("/");
    apiGetMock.mockResolvedValue({
      active: { source: "samples", profiles: [], profile_key: "samples__empty" },
      options: { default: [], samples: [] },
    });
  });

  it("renders nav items and highlights active route", async () => {
    render(
      <Shell>
        <div>Contenido</div>
      </Shell>
    );

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Sentimiento")).toBeInTheDocument();
    expect(screen.getByText("Global Overview Radar")).toBeInTheDocument();
  });
});
