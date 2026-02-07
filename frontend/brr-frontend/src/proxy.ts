import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_LOG_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

function normalizeIapEmail(value: string | null): string | null {
  if (!value) return null;
  return value.replace(/^accounts\.google\.com:/, "");
}

function normalizeIapId(value: string | null): string | null {
  if (!value) return null;
  return value.replace(/^accounts\.google\.com:/, "");
}

export function proxy(request: NextRequest) {
  if (!AUTH_LOG_ENABLED) {
    return NextResponse.next();
  }
  const email = normalizeIapEmail(request.headers.get("x-goog-authenticated-user-email"));
  const userId = normalizeIapId(request.headers.get("x-goog-authenticated-user-id"));
  const forwardedFor = request.headers.get("x-forwarded-for");
  const clientIp = forwardedFor ? forwardedFor.split(",")[0]?.trim() : null;
  const requestIp = (request as unknown as { ip?: string }).ip ?? null;
  const resolvedIp = clientIp ?? requestIp ?? null;
  const userAgent = request.headers.get("user-agent");

  console.log(
    JSON.stringify({
      event: "iap_access",
      path: request.nextUrl.pathname,
      method: request.method,
      email: email ?? "unknown",
      userId: userId ?? null,
      ip: resolvedIp ?? "unknown",
      ipForwarded: clientIp ?? null,
      ipRequest: requestIp ?? null,
      userAgent: userAgent ?? "unknown",
      timestamp: new Date().toISOString(),
    })
  );

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|api|favicon.ico).*)"],
};
