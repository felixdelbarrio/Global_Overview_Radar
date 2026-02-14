/**
 * Cliente HTTP del frontend.
 *
 * Centraliza la construccion de URLs y manejo de errores.
 */

import { logger } from "@/lib/logger";
import {
  clearStoredToken,
  getStoredToken,
  isTokenExpired,
} from "@/lib/auth";

/** Base de la API; permite proxy local con /api. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
const LOGIN_REQUIRED = process.env.NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED === "true";
const RETRIABLE_GET_STATUS = new Set([429, 502, 503, 504]);
const API_GET_MAX_ATTEMPTS = 3;
const API_GET_BASE_RETRY_DELAY_MS = 450;
const API_GET_MAX_RETRY_DELAY_MS = 4000;

export class ApiError extends Error {
  status: number;
  path: string;
  retryAfterMs: number | null;

  constructor(path: string, status: number, detail: string, retryAfterMs: number | null) {
    super(`API ${path} failed: ${status}${detail ? ` — ${detail}` : ""}`);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
    this.retryAfterMs = retryAfterMs;
  }
}

function resolveUserToken(): string | null {
  if (!LOGIN_REQUIRED) {
    clearStoredToken();
    return null;
  }
  const token = getStoredToken();
  if (!token) return null;
  if (isTokenExpired(token)) {
    clearStoredToken();
    return null;
  }
  return token;
}

logger.info("API_BASE", { apiBase: API_BASE });

type CacheEntry = {
  expiresAt: number;
  value?: unknown;
  promise?: Promise<unknown>;
};

const API_CACHE = new Map<string, CacheEntry>();

function readHeader(response: Response, header: string): string | null {
  const headers = (response as unknown as { headers?: { get?: (name: string) => string | null } })
    .headers;
  if (!headers || typeof headers.get !== "function") return null;
  return headers.get(header);
}

function parseRetryAfterMs(value: string | null): number | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const seconds = Number(trimmed);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.round(seconds * 1000);
  }
  const parsedDate = Date.parse(trimmed);
  if (Number.isNaN(parsedDate)) return null;
  return Math.max(0, parsedDate - Date.now());
}

function retryDelayMs(attempt: number, retryAfterMs: number | null): number {
  const exponential = Math.min(
    API_GET_MAX_RETRY_DELAY_MS,
    API_GET_BASE_RETRY_DELAY_MS * 2 ** Math.max(0, attempt - 1),
  );
  const jitter = Math.round(exponential * (0.8 + Math.random() * 0.4));
  if (retryAfterMs === null) return jitter;
  return Math.min(API_GET_MAX_RETRY_DELAY_MS, Math.max(retryAfterMs, API_GET_BASE_RETRY_DELAY_MS));
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function parseApiError(path: string, response: Response): Promise<ApiError> {
  const detail = await response.text().catch(() => "");
  const retryAfterMs = parseRetryAfterMs(readHeader(response, "retry-after"));
  return new ApiError(path, response.status, detail, retryAfterMs);
}

/**
 * Ejecuta un GET y devuelve JSON tipado.
 * @param path Ruta relativa del endpoint.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const token = resolveUserToken();
  for (let attempt = 1; attempt <= API_GET_MAX_ATTEMPTS; attempt += 1) {
    logger.debug("apiGet -> request", () => ({ path, url, attempt }));
    const res = await fetch(url, {
      cache: "no-store",
      headers:
        token
          ? {
              ...(token ? { "x-user-id-token": token } : {}),
            }
          : undefined,
    });

    if (res.ok) {
      logger.debug("apiGet -> ok", () => ({ path, status: res.status, attempt }));
      return (await res.json()) as T;
    }

    const apiError = await parseApiError(path, res);
    logger.warn("apiGet -> error", () => ({
      path,
      status: apiError.status,
      detail: apiError.message,
      attempt,
    }));
    if (LOGIN_REQUIRED && apiError.status === 401) {
      // When ID tokens expire or the backend rejects them, clear local auth so AuthGate can re-login.
      clearStoredToken();
    }
    const retryable = RETRIABLE_GET_STATUS.has(apiError.status) && attempt < API_GET_MAX_ATTEMPTS;
    if (!retryable) {
      throw apiError;
    }
    const waitMs = retryDelayMs(attempt, apiError.retryAfterMs);
    logger.warn("apiGet -> retry", () => ({
      path,
      status: apiError.status,
      attempt,
      waitMs,
    }));
    await sleep(waitMs);
  }
  throw new ApiError(path, 500, "unexpected retry exhaustion", null);
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

  logger.debug("apiPost -> request", () => ({ path, url, body }));
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "x-user-id-token": token } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    const apiError = await parseApiError(path, res);
    logger.warn("apiPost -> error", () => ({
      path,
      status: apiError.status,
      detail: apiError.message,
    }));
    if (LOGIN_REQUIRED && res.status === 401) {
      clearStoredToken();
    }
    throw apiError;
  }

  logger.debug("apiPost -> ok", () => ({ path, status: res.status }));
  return (await res.json()) as T;
}
