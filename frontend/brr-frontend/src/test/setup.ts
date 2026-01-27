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
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Mock de alert para acciones demo.
if (!window.alert) {
  window.alert = vi.fn();
}
