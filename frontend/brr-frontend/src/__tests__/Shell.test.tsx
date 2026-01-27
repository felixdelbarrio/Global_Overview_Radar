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

import { usePathname } from "next/navigation";
import { Shell } from "@/components/Shell";

const usePathnameMock = vi.mocked(usePathname);

describe("Shell", () => {
  beforeEach(() => {
    usePathnameMock.mockReturnValue("/ops");
  });

  it("renders nav items and highlights active route", () => {
    render(
      <Shell>
        <div>Contenido</div>
      </Shell>
    );

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Incidencias")).toBeInTheDocument();
    const ops = screen.getByText("Ops Executive");
    expect(ops).toBeInTheDocument();

    const opsLink = ops.closest("a");
    expect(opsLink?.className).toContain("text-white");
  });
});
