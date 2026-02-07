import { NextResponse, type NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const METADATA_IDENTITY_URL =
  "http://metadata/computeMetadata/v1/instance/service-accounts/default/identity";

const DEFAULT_LOCAL_API = "http://127.0.0.1:8000";
const DEFAULT_RENDER_API = "https://global-overview-radar.onrender.com";

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

async function fetchIdToken(audience: string): Promise<string> {
  const url = `${METADATA_IDENTITY_URL}?audience=${encodeURIComponent(
    audience,
  )}&format=full`;
  const res = await fetch(url, {
    headers: { "Metadata-Flavor": "Google" },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`metadata identity token failed (${res.status}): ${text}`);
  }
  return res.text();
}

function shouldUseIdToken(): boolean {
  return process.env.USE_SERVER_PROXY === "true";
}

async function proxyRequest(request: NextRequest, path: string[]): Promise<Response> {
  const target = resolveProxyTarget();
  const url = buildTargetUrl(target, path, new URL(request.url).search);
  const headers = sanitizeHeaders(new Headers(request.headers));

  if (shouldUseIdToken()) {
    const idToken = await fetchIdToken(target);
    headers.set("authorization", `Bearer ${idToken}`);
  }

  const method = request.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();

  const upstream = await fetch(url, {
    method,
    headers,
    body,
    redirect: "manual",
  });

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
