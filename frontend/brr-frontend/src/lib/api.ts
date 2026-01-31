/**
 * Cliente HTTP del frontend.
 *
 * Centraliza la construccion de URLs y manejo de errores.
 */

/** Base de la API; permite proxy local con /api. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

/**
 * Ejecuta un GET y devuelve JSON tipado.
 * @param path Ruta relativa del endpoint.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  const res = await fetch(url, { cache: "no-store" });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} failed: ${res.status}${text ? ` — ${text}` : ""}`);
  }

  return (await res.json()) as T;
}

/**
 * Ejecuta un POST con JSON y devuelve JSON tipado.
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} failed: ${res.status}${text ? ` — ${text}` : ""}`);
  }

  return (await res.json()) as T;
}
