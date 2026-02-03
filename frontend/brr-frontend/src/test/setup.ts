/** Setup global de pruebas (JSDOM y mocks basicos). */

import "@testing-library/jest-dom/vitest";
import * as React from "react";
import { vi } from "vitest";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({
      width,
      height,
      children,
    }: {
      width?: number | string;
      height?: number | string;
      children?: React.ReactNode;
    }) => {
      const resolvedWidth = typeof width === "number" ? width : 800;
      const resolvedHeight = typeof height === "number" ? height : 400;
      return React.createElement(
        "div",
        { style: { width: resolvedWidth, height: resolvedHeight } },
        React.Children.map(children, (child) =>
          React.isValidElement(child)
            ? React.cloneElement(child, {
                width: resolvedWidth,
                height: resolvedHeight,
              })
            : child
        )
      );
    },
  };
});

// Mock de matchMedia para componentes que dependen de media queries.
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
}

// Mock de ResizeObserver usado por librerias de charts/layout.
if (!window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserverMock {
    private callback: ResizeObserverCallback;

    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
    }

    observe(target: Element) {
      const rect = target.getBoundingClientRect();
      const width = rect.width > 0 ? rect.width : 640;
      const height = rect.height > 0 ? rect.height : 360;
      const entry = [
        {
          target,
          contentRect: { width, height } as DOMRectReadOnly,
        } as ResizeObserverEntry,
      ];
      this.callback(entry, this as unknown as ResizeObserver);
    }

    unobserve() {}
    disconnect() {}
  };
}

// Mock de alert para acciones demo.
if (!window.alert) {
  window.alert = vi.fn();
}
