import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export const runtime = "nodejs";

const TOKEN_KEY = "gor-google-id-token";
const EMAIL_KEY = "gor-google-email";
const NEXT_COOKIE = "gor-login-next";
const FALLBACK_ROUTE = "/";

function sanitizeNextPath(value: string | null): string {
  if (!value) return FALLBACK_ROUTE;
  if (!value.startsWith("/")) return FALLBACK_ROUTE;
  if (value.startsWith("//")) return FALLBACK_ROUTE;
  if (value.toLowerCase().startsWith("/\\") || value.toLowerCase().includes("://")) {
    return FALLBACK_ROUTE;
  }
  return value;
}

function buildHtml(token: string, nextPath: string): string {
  const tokenJson = JSON.stringify(token);
  const nextJson = JSON.stringify(nextPath);
  return `<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Acceso</title>
  </head>
  <body>
    <script>
      (function () {
        var token = ${tokenJson};
        var nextPath = ${nextJson};
        function safeStorage() {
          try {
            var s = window.sessionStorage;
            var k = "__gor_test__";
            s.setItem(k, "1");
            s.removeItem(k);
            return s;
          } catch (err) {}
          try {
            var l = window.localStorage;
            var k2 = "__gor_test__";
            l.setItem(k2, "1");
            l.removeItem(k2);
            return l;
          } catch (err2) {}
          return null;
        }
        function decodeEmail(value) {
          try {
            var parts = value.split(".");
            if (parts.length < 2) return null;
            var base = parts[1].replace(/-/g, "+").replace(/_/g, "/");
            var padded = base.padEnd(Math.ceil(base.length / 4) * 4, "=");
            var json = window.atob(padded);
            var payload = JSON.parse(json);
            return payload && payload.email ? payload.email : null;
          } catch (err3) {
            return null;
          }
        }
        var storage = safeStorage();
        if (storage && token) {
          storage.setItem(${JSON.stringify(TOKEN_KEY)}, token);
          var email = decodeEmail(token);
          if (email) {
            storage.setItem(${JSON.stringify(EMAIL_KEY)}, email);
          }
        }
        window.location.replace(nextPath || "/");
      })();
    </script>
  </body>
</html>`;
}

export async function POST(request: Request) {
  const form = await request.formData();
  const credential = String(form.get("credential") ?? "");
  if (!credential) {
    return new NextResponse("Missing credential", { status: 400 });
  }

  const cookieStore = await cookies();
  const csrfForm = String(form.get("g_csrf_token") ?? "");
  const csrfCookie = cookieStore.get("g_csrf_token")?.value ?? "";
  if (csrfForm && csrfCookie && csrfForm !== csrfCookie) {
    return new NextResponse("Invalid CSRF token", { status: 400 });
  }

  const nextPath = sanitizeNextPath(cookieStore.get(NEXT_COOKIE)?.value ?? null);
  const html = buildHtml(credential, nextPath);
  const response = new NextResponse(html, {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
  response.cookies.set(NEXT_COOKIE, "", { maxAge: 0, path: "/" });
  response.cookies.set("g_csrf_token", "", { maxAge: 0, path: "/" });
  return response;
}
