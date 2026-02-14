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
  apiGetCached: vi.fn(),
  apiPost: vi.fn(),
}));

import { usePathname } from "next/navigation";
import { apiGet, apiGetCached } from "@/lib/api";
import { Shell } from "@/components/Shell";

const usePathnameMock = vi.mocked(usePathname);
const apiGetMock = vi.mocked(apiGet);
const apiGetCachedMock = vi.mocked(apiGetCached);

describe("Shell", () => {
  beforeEach(() => {
    usePathnameMock.mockReturnValue("/");
    apiGetMock.mockResolvedValue({});
    apiGetCachedMock.mockResolvedValue({});
  });

  it("renders nav items and highlights active route", async () => {
    render(
      <Shell>
        <div>Contenido</div>
      </Shell>
    );

    expect(screen.getAllByRole("link", { name: "Dashboard" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Sentimiento Markets" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Sentimiento Prensa" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Respuestas en Markets" }).length).toBeGreaterThan(0);
  });
});
