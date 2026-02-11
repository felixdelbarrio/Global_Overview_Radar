import { NextResponse, type NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const METADATA_IDENTITY_URL =
  "http://metadata/computeMetadata/v1/instance/service-accounts/default/identity";

const DEFAULT_LOCAL_API = "http://127.0.0.1:8000";
const DEFAULT_RENDER_API = "https://global-overview-radar.onrender.com";
const LOGIN_REQUIRED = process.env.NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED === "true";
const AUTH_BYPASS = !LOGIN_REQUIRED;
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const PROXY_AUTH_HEADER = "x-gor-proxy-auth";
const PROXY_AUTH_CLOUD_RUN = "cloudrun-idtoken";

const METADATA_TIMEOUT_MS = 3000;
const UPSTREAM_TIMEOUT_MS = 30000;
const ID_TOKEN_TTL_MS = 50 * 60 * 1000; // conservative cache under typical 1h lifetime

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function sanitizeHeaders(headers: Headers): Headers {
  const sanitized = new Headers(headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    sanitized.delete(header);
  }
  sanitized.delete("host");
  sanitized.delete("content-length");
  // Never forward browser cookies to the backend.
  sanitized.delete("cookie");
  if (!AUTH_BYPASS) {
    sanitized.delete("x-gor-admin-key");
  }
  // Internal marker added by the server proxy (never forward client-supplied values).
  sanitized.delete(PROXY_AUTH_HEADER);
  if (AUTH_BYPASS) {
    sanitized.delete("x-user-id-token");
    sanitized.delete("x-user-token");
  }
  return sanitized;
}

function resolveProxyTarget(): string {
  const fallback = process.env.VERCEL ? DEFAULT_RENDER_API : DEFAULT_LOCAL_API;
  const raw = process.env.API_PROXY_TARGET || fallback;
  return raw.replace(/\/+$/, "");
}

function buildTargetUrl(target: string, path: string[], search: string): string {
  const joined = path.map((segment) => segment.replace(/^\/+|\/+$/g, "")).join("/");
  const suffix = joined ? `/${joined}` : "";
  return `${target}${suffix}${search || ""}`;
}

function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...init, signal: controller.signal }).finally(() => clearTimeout(timeout));
}

let _cachedIdToken: { audience: string; token: string; expiresAt: number } | null = null;
let _cachedIdTokenPromise: Promise<string> | null = null;

async function fetchIdToken(audience: string): Promise<string> {
  const now = Date.now();
  if (_cachedIdToken && _cachedIdToken.audience === audience && _cachedIdToken.expiresAt > now) {
    return _cachedIdToken.token;
  }
  if (_cachedIdTokenPromise) {
    return _cachedIdTokenPromise;
  }
  const url = `${METADATA_IDENTITY_URL}?audience=${encodeURIComponent(
    audience,
  )}&format=full`;
  _cachedIdTokenPromise = (async () => {
    const res = await fetchWithTimeout(
      url,
      { headers: { "Metadata-Flavor": "Google" } },
      METADATA_TIMEOUT_MS,
    );
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`metadata identity token failed (${res.status}): ${text}`);
    }
    const token = (await res.text()).trim();
    _cachedIdToken = { audience, token, expiresAt: Date.now() + ID_TOKEN_TTL_MS };
    return token;
  })().finally(() => {
    _cachedIdTokenPromise = null;
  });
  return _cachedIdTokenPromise;
}

function shouldUseIdToken(): boolean {
  return process.env.USE_SERVER_PROXY === "true";
}

async function proxyRequest(request: NextRequest, path: string[]): Promise<Response> {
  const method = request.method.toUpperCase();
  const adminKey = request.headers.get("x-gor-admin-key");
  const hasAdminKey = Boolean(adminKey && adminKey.trim());
  if (AUTH_BYPASS && MUTATING_METHODS.has(method) && !hasAdminKey) {
    return NextResponse.json(
      {
        detail:
          "Mutating API routes require x-gor-admin-key while GOOGLE_CLOUD_LOGIN_REQUESTED=false.",
      },
      { status: 403 },
    );
  }

  const target = resolveProxyTarget();
  const url = buildTargetUrl(target, path, new URL(request.url).search);
  const headers = sanitizeHeaders(new Headers(request.headers));

  if (shouldUseIdToken()) {
    const idToken = await fetchIdToken(target);
    headers.set("authorization", `Bearer ${idToken}`);
    headers.set(PROXY_AUTH_HEADER, PROXY_AUTH_CLOUD_RUN);
  }

  const body =
    method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();

  const upstream = await fetchWithTimeout(
    url,
    {
      method,
      headers,
      body,
      redirect: "manual",
    },
    UPSTREAM_TIMEOUT_MS,
  );

  const responseHeaders = sanitizeHeaders(new Headers(upstream.headers));
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

type RouteParams = { params: Promise<{ path: string[] }> };

async function resolvePath(params: RouteParams): Promise<string[]> {
  const resolved = await params.params;
  return Array.isArray(resolved?.path) ? resolved.path : [];
}

export async function GET(request: NextRequest, params: RouteParams) {
  return proxyRequest(request, await resolvePath(params));
}

export async function POST(request: NextRequest, params: RouteParams) {
  return proxyRequest(request, await resolvePath(params));
}

export async function PUT(request: NextRequest, params: RouteParams) {
  return proxyRequest(request, await resolvePath(params));
}

export async function PATCH(request: NextRequest, params: RouteParams) {
  return proxyRequest(request, await resolvePath(params));
}

export async function DELETE(request: NextRequest, params: RouteParams) {
  return proxyRequest(request, await resolvePath(params));
}

export async function OPTIONS(request: NextRequest, params: RouteParams) {
  return proxyRequest(request, await resolvePath(params));
}
