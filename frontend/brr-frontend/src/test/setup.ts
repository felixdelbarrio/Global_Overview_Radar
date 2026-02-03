/** Setup global de pruebas (JSDOM y mocks basicos). */

import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

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
