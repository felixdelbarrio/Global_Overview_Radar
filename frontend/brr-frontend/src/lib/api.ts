/**
 * Cliente HTTP del frontend.
 *
 * Centraliza la construccion de URLs y manejo de errores.
 */

import { logger } from "@/lib/logger";

/** Base de la API; permite proxy local con /api. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

/**
 * Ejecuta un GET y devuelve JSON tipado.
 * @param path Ruta relativa del endpoint.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  logger.debug("apiGet -> request", () => ({ path, url }));
  const res = await fetch(url, { cache: "no-store" });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    logger.warn("apiGet -> error", () => ({ path, status: res.status, text }));
    throw new Error(`API ${path} failed: ${res.status}${text ? ` — ${text}` : ""}`);
  }

  logger.debug("apiGet -> ok", () => ({ path, status: res.status }));
  return (await res.json()) as T;
}

/**
 * Ejecuta un POST con JSON y devuelve JSON tipado.
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  logger.debug("apiPost -> request", () => ({ path, url, body }));
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    logger.warn("apiPost -> error", () => ({ path, status: res.status, text }));
    throw new Error(`API ${path} failed: ${res.status}${text ? ` — ${text}` : ""}`);
  }

  logger.debug("apiPost -> ok", () => ({ path, status: res.status }));
  return (await res.json()) as T;
}
