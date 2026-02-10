/**
 * Cliente HTTP del frontend.
 *
 * Centraliza la construccion de URLs y manejo de errores.
 */

import { logger } from "@/lib/logger";
import {
  clearStoredToken,
  getStoredAdminKey,
  getStoredToken,
} from "@/lib/auth";

/** Base de la API; permite proxy local con /api. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
const LOGIN_REQUIRED = process.env.NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED === "true";
const AUTH_BYPASS = !LOGIN_REQUIRED;
const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true" && LOGIN_REQUIRED;

function resolveUserToken(): string | null {
  if (!AUTH_ENABLED) {
    clearStoredToken();
    return null;
  }
  return getStoredToken();
}

function resolveAdminKey(): string | null {
  if (!AUTH_BYPASS) return null;
  return getStoredAdminKey();
}

logger.info("API_BASE", { apiBase: API_BASE });

type CacheEntry = {
  expiresAt: number;
  value?: unknown;
  promise?: Promise<unknown>;
};

const API_CACHE = new Map<string, CacheEntry>();

/**
 * Ejecuta un GET y devuelve JSON tipado.
 * @param path Ruta relativa del endpoint.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const token = resolveUserToken();
  const adminKey = resolveAdminKey();

  logger.debug("apiGet -> request", () => ({ path, url }));
  const res = await fetch(url, {
    cache: "no-store",
    headers:
      token || adminKey
        ? {
            ...(token ? { "x-user-id-token": token } : {}),
            ...(adminKey ? { "x-gor-admin-key": adminKey } : {}),
          }
        : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    logger.warn("apiGet -> error", () => ({ path, status: res.status, text }));
    throw new Error(`API ${path} failed: ${res.status}${text ? ` — ${text}` : ""}`);
  }

  logger.debug("apiGet -> ok", () => ({ path, status: res.status }));
  return (await res.json()) as T;
}

export async function apiGetCached<T>(
  path: string,
  options?: { ttlMs?: number; force?: boolean }
): Promise<T> {
  const ttlMs = options?.ttlMs ?? 60000;
  const token = resolveUserToken();
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const cacheKey = `${token ?? "anon"}:${url}`;
  const now = Date.now();

  if (!options?.force) {
    const cached = API_CACHE.get(cacheKey);
    if (cached) {
      if (cached.value !== undefined && cached.expiresAt > now) {
        return cached.value as T;
      }
      if (cached.promise) {
        return cached.promise as Promise<T>;
      }
    }
  }

  const promise = apiGet<T>(path)
    .then((value) => {
      API_CACHE.set(cacheKey, { value, expiresAt: now + ttlMs });
      return value;
    })
    .catch((err) => {
      API_CACHE.delete(cacheKey);
      throw err;
    });

  API_CACHE.set(cacheKey, { promise, expiresAt: now + ttlMs });
  return promise;
}

export function clearApiCache(): void {
  API_CACHE.clear();
}

/**
 * Ejecuta un POST con JSON y devuelve JSON tipado.
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const token = resolveUserToken();
  const adminKey = resolveAdminKey();

  logger.debug("apiPost -> request", () => ({ path, url, body }));
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "x-user-id-token": token } : {}),
      ...(adminKey ? { "x-gor-admin-key": adminKey } : {}),
    },
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
