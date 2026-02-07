"use client";

import { useEffect, useRef, useState } from "react";
import Script from "next/script";
import { usePathname, useRouter } from "next/navigation";
import { apiGet } from "@/lib/api";
import {
  clearStoredToken,
  getEmailFromToken,
  getStoredToken,
  isEmailAllowed,
  isTokenExpired,
  storeToken,
} from "@/lib/auth";

type CredentialResponse = { credential?: string };

const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";
const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";
const FALLBACK_ROUTE = "/";

type AuthMeResponse = {
  email: string;
  name?: string | null;
  picture?: string | null;
  subject?: string | null;
};

function sanitizeNextPath(value: string | null): string {
  if (!value) return FALLBACK_ROUTE;
  if (!value.startsWith("/")) return FALLBACK_ROUTE;
  if (value.startsWith("//")) return FALLBACK_ROUTE;
  if (value.toLowerCase().startsWith("/\\") || value.toLowerCase().includes("://")) {
    return FALLBACK_ROUTE;
  }
  return value;
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const buttonRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const lastVerifiedToken = useRef<string | null>(null);
  const [verifiedToken, setVerifiedToken] = useState<string | null>(null);
  const [verificationErrorToken, setVerificationErrorToken] = useState<string | null>(null);
  const [auth, setAuth] = useState<{
    token: string | null;
    email: string | null;
    shouldClear: boolean;
  }>(() => {
    if (!AUTH_ENABLED || typeof window === "undefined") {
      return { token: null, email: null, shouldClear: false };
    }
    const stored = getStoredToken();
    if (!stored || isTokenExpired(stored)) {
      return { token: null, email: null, shouldClear: Boolean(stored) };
    }
    const storedEmail = getEmailFromToken(stored);
    if (storedEmail && isEmailAllowed(storedEmail)) {
      return { token: stored, email: storedEmail, shouldClear: false };
    }
    return { token: null, email: null, shouldClear: true };
  });
  const { token, email } = auth;
  const [error, setError] = useState<string | null>(null);
  const isLoginPage = pathname === "/login";
  const isVerified = Boolean(token) && verifiedToken === token;
  const hasVerificationError = Boolean(token) && verificationErrorToken === token;
  const serverStatus: "idle" | "checking" | "ok" | "error" = !token
    ? "idle"
    : isVerified
      ? "ok"
      : hasVerificationError
        ? "error"
        : "checking";

  useEffect(() => {
    if (!auth.shouldClear) return;
    clearStoredToken();
  }, [auth.shouldClear]);

  useEffect(() => {
    if (!AUTH_ENABLED) return;
    if (token) return;
    if (isLoginPage) return;
    const search = typeof window !== "undefined" ? window.location.search : "";
    const target = search ? `${pathname}${search}` : pathname;
    router.replace(`/login?next=${encodeURIComponent(target)}`);
  }, [token, isLoginPage, pathname, router]);

  useEffect(() => {
    if (!AUTH_ENABLED) return;
    if (!token) return;
    if (!isLoginPage) return;
    const params =
      typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
    const nextParam = params?.get("next") || "/";
    router.replace(sanitizeNextPath(nextParam));
  }, [token, isLoginPage, router]);

  useEffect(() => {
    if (!AUTH_ENABLED || !CLIENT_ID || !ready) return;
    if (!window.google?.accounts?.id) return;

    window.google.accounts.id.initialize({
      client_id: CLIENT_ID,
      callback: (response: CredentialResponse) => {
        const credential = response?.credential;
        if (!credential) {
          setError("No se pudo obtener el token de Google.");
          return;
        }
        if (isTokenExpired(credential)) {
          setError("El token de Google ha expirado. Inténtalo de nuevo.");
          return;
        }
        const nextEmail = getEmailFromToken(credential);
        if (!nextEmail) {
          setError("No se pudo leer el email del token.");
          return;
        }
        if (!isEmailAllowed(nextEmail)) {
          clearStoredToken();
          setAuth({ token: null, email: null, shouldClear: false });
          setError(`El correo ${nextEmail} no está autorizado.`);
          return;
        }
        storeToken(credential, nextEmail);
        setAuth({ token: credential, email: nextEmail, shouldClear: false });
        setError(null);
      },
      auto_select: false,
      ux_mode: "popup",
    });

    if (buttonRef.current) {
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
        shape: "pill",
        text: "signin_with",
      });
    }
  }, [ready]);

  useEffect(() => {
    if (!AUTH_ENABLED) return;
    if (!token) {
      lastVerifiedToken.current = null;
      return;
    }
    if (lastVerifiedToken.current === token) return;
    let alive = true;
    apiGet<AuthMeResponse>("/auth/me")
      .then(() => {
        if (!alive) return;
        lastVerifiedToken.current = token;
        setVerifiedToken(token);
        setVerificationErrorToken(null);
      })
      .catch(() => {
        if (!alive) return;
        clearStoredToken();
        setAuth({ token: null, email: null, shouldClear: false });
        setError("No se pudo validar permisos con el backend.");
        setVerifiedToken(null);
        setVerificationErrorToken(token);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  const handleLogout = () => {
    clearStoredToken();
    setAuth({ token: null, email: null, shouldClear: false });
    setError(null);
    if (window.google?.accounts?.id) {
      window.google.accounts.id.disableAutoSelect();
    }
  };

  if (!AUTH_ENABLED) {
    return <>{children}</>;
  }

  if (!CLIENT_ID) {
    return (
      <div className="min-h-screen grid place-items-center bg-[color:var(--surface-90)]">
        <div className="max-w-md rounded-3xl border border-[color:var(--border-70)] bg-[color:var(--surface-85)] p-6 text-sm text-[color:var(--text-65)]">
          Falta configurar `NEXT_PUBLIC_GOOGLE_CLIENT_ID`.
        </div>
      </div>
    );
  }

  if (token && serverStatus === "checking") {
    return (
      <>
        <Script
          src="https://accounts.google.com/gsi/client"
          strategy="afterInteractive"
          onLoad={() => setReady(true)}
        />
        <div className="min-h-screen grid place-items-center bg-[color:var(--surface-90)] px-6">
          <div className="w-full max-w-md rounded-3xl border border-[color:var(--border-70)] bg-[color:var(--surface-85)] p-6 text-sm text-[color:var(--text-60)]">
            Validando permisos...
          </div>
        </div>
      </>
    );
  }

  if (token && serverStatus === "ok") {
    return (
      <>
        <Script
          src="https://accounts.google.com/gsi/client"
          strategy="afterInteractive"
          onLoad={() => setReady(true)}
        />
        <div className="min-h-screen">
          <div className="fixed right-4 top-4 z-50 rounded-full border border-[color:var(--border-70)] bg-[color:var(--surface-90)] px-3 py-1.5 text-xs text-[color:var(--text-55)] shadow-[var(--shadow-pill)]">
            {email ? `Conectado: ${email}` : "Conectado"}
            <button
              className="ml-3 text-[color:var(--aqua)] hover:text-[color:var(--blue)]"
              onClick={handleLogout}
            >
              Salir
            </button>
          </div>
          {children}
        </div>
      </>
    );
  }

  if (!isLoginPage) {
    return (
      <>
        <Script
          src="https://accounts.google.com/gsi/client"
          strategy="afterInteractive"
          onLoad={() => setReady(true)}
        />
        <div className="min-h-screen grid place-items-center bg-[color:var(--surface-90)] px-6">
          <div className="w-full max-w-md rounded-3xl border border-[color:var(--border-70)] bg-[color:var(--surface-85)] p-6 text-sm text-[color:var(--text-60)]">
            Redirigiendo al inicio de sesión...
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onLoad={() => setReady(true)}
      />
      <div className="min-h-screen grid place-items-center bg-[color:var(--surface-90)] px-6">
        <div className="w-full max-w-md rounded-3xl border border-[color:var(--border-70)] bg-[color:var(--surface-85)] p-6 shadow-[var(--shadow-card)]">
          <div className="text-lg font-semibold text-[color:var(--ink)]">
            Acceso restringido
          </div>
          <p className="mt-2 text-sm text-[color:var(--text-60)]">
            Inicia sesión con tu cuenta de Gmail autorizada para continuar.
          </p>
          <div className="mt-4" ref={buttonRef} />
          {error ? (
            <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}
