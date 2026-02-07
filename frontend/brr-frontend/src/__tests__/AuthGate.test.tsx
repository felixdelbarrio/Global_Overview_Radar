/** Tests del componente AuthGate. */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
const usePathnameMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => usePathnameMock(),
}));

vi.mock("next/script", () => ({
  default: ({ onLoad }: { onLoad?: () => void }) => {
    React.useEffect(() => {
      onLoad?.();
    }, [onLoad]);
    return null;
  },
}));

const authMocks = {
  clearStoredToken: vi.fn(),
  getEmailFromToken: vi.fn(),
  getStoredToken: vi.fn(),
  isEmailAllowed: vi.fn(),
  isTokenExpired: vi.fn(),
  storeToken: vi.fn(),
};

vi.mock("@/lib/auth", () => authMocks);

const originalEnv = { ...process.env };

const loadAuthGate = async (env: Record<string, string | undefined>) => {
  vi.resetModules();
  process.env = { ...originalEnv, ...env };
  const mod = await import("@/components/AuthGate");
  return mod.AuthGate;
};

beforeEach(() => {
  replaceMock.mockReset();
  usePathnameMock.mockReturnValue("/");
  authMocks.clearStoredToken.mockReset();
  authMocks.getEmailFromToken.mockReset();
  authMocks.getStoredToken.mockReset();
  authMocks.isEmailAllowed.mockReset();
  authMocks.isTokenExpired.mockReset();
  authMocks.storeToken.mockReset();
  authMocks.isTokenExpired.mockReturnValue(false);
  authMocks.isEmailAllowed.mockReturnValue(true);
  authMocks.getEmailFromToken.mockReturnValue("user@bbva.com");
  authMocks.getStoredToken.mockReturnValue(null);
  (window as any).google = undefined;
  window.history.pushState({}, "", "/");
});

afterEach(() => {
  process.env = { ...originalEnv };
});

describe("AuthGate", () => {
  it("renders children when auth is disabled", async () => {
    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "false",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    expect(screen.getByText("Contenido")).toBeInTheDocument();
  });

  it("shows missing client id message when enabled without client id", async () => {
    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    expect(
      screen.getByText("Falta configurar `NEXT_PUBLIC_GOOGLE_CLIENT_ID`.")
    ).toBeInTheDocument();
  });

  it("shows login screen when unauthenticated on /login", async () => {
    usePathnameMock.mockReturnValue("/login");
    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    expect(screen.getByText("Acceso restringido")).toBeInTheDocument();
  });

  it("redirects to login when unauthenticated on other routes", async () => {
    usePathnameMock.mockReturnValue("/dashboard");
    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/login?next=%2Fdashboard");
    });
  });

  it("redirects to login preserving query string", async () => {
    usePathnameMock.mockReturnValue("/dashboard");
    window.history.pushState({}, "", "/dashboard?foo=1");
    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/login?next=%2Fdashboard%3Ffoo%3D1");
    });
  });

  it("clears stored token when session is expired", async () => {
    authMocks.getStoredToken.mockReturnValue("token");
    authMocks.isTokenExpired.mockReturnValue(true);

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(authMocks.clearStoredToken).toHaveBeenCalled();
    });
  });

  it("clears stored token when email is not allowed", async () => {
    authMocks.getStoredToken.mockReturnValue("token");
    authMocks.isTokenExpired.mockReturnValue(false);
    authMocks.getEmailFromToken.mockReturnValue("user@evil.com");
    authMocks.isEmailAllowed.mockReturnValue(false);

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(authMocks.clearStoredToken).toHaveBeenCalled();
    });
  });

  it("renders logged-in state and supports logout", async () => {
    authMocks.getStoredToken.mockReturnValue("token");
    const disableAutoSelect = vi.fn();
    const initialize = vi.fn();
    (window as any).google = {
      accounts: { id: { disableAutoSelect, initialize } },
    };

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    expect(screen.getByText("Conectado: user@bbva.com")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Salir" }));
    expect(authMocks.clearStoredToken).toHaveBeenCalled();
    expect(disableAutoSelect).toHaveBeenCalled();
  });

  it("sanitizes next param when redirecting from login", async () => {
    usePathnameMock.mockReturnValue("/login");
    authMocks.getStoredToken.mockReturnValue("token");
    window.history.pushState({}, "", "/login?next=//evil.com");

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
  });

  it("sanitizes next param with protocol", async () => {
    usePathnameMock.mockReturnValue("/login");
    authMocks.getStoredToken.mockReturnValue("token");
    window.history.pushState({}, "", "/login?next=http://evil.com");

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
  });

  it("sanitizes next param without leading slash", async () => {
    usePathnameMock.mockReturnValue("/login");
    authMocks.getStoredToken.mockReturnValue("token");
    window.history.pushState({}, "", "/login?next=foo");

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
  });

  it("allows safe next param redirects", async () => {
    usePathnameMock.mockReturnValue("/login");
    authMocks.getStoredToken.mockReturnValue("token");
    window.history.pushState({}, "", "/login?next=/sentimiento");

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/sentimiento");
    });
  });

  it("sanitizes next param with backslash prefix", async () => {
    usePathnameMock.mockReturnValue("/login");
    authMocks.getStoredToken.mockReturnValue("token");
    window.history.pushState({}, "", "/login?next=/\\\\evil");

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
  });

  it("initializes google and surfaces callback errors", async () => {
    usePathnameMock.mockReturnValue("/login");
    authMocks.getStoredToken.mockReturnValue(null);

    let captured: ((response: { credential?: string }) => void) | null = null;
    const initialize = vi.fn(({ callback }: { callback: (r: { credential?: string }) => void }) => {
      captured = callback;
    });
    const renderButton = vi.fn();
    (window as any).google = {
      accounts: { id: { initialize, renderButton } },
    };

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_AUTH_ENABLED: "true",
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(initialize).toHaveBeenCalled();
      expect(renderButton).toHaveBeenCalled();
    });

    captured?.({});
    expect(await screen.findByText("No se pudo obtener el token de Google."))
      .toBeInTheDocument();

    authMocks.isTokenExpired.mockReturnValueOnce(true);
    captured?.({ credential: "token" });
    expect(
      await screen.findByText("El token de Google ha expirado. Inténtalo de nuevo.")
    ).toBeInTheDocument();

    authMocks.isTokenExpired.mockReturnValueOnce(false);
    authMocks.getEmailFromToken.mockReturnValueOnce(null);
    captured?.({ credential: "token" });
    expect(await screen.findByText("No se pudo leer el email del token."))
      .toBeInTheDocument();

    authMocks.getEmailFromToken.mockReturnValueOnce("user@evil.com");
    authMocks.isEmailAllowed.mockReturnValueOnce(false);
    captured?.({ credential: "token" });
    expect(
      await screen.findByText("El correo user@evil.com no está autorizado.")
    ).toBeInTheDocument();
    expect(authMocks.clearStoredToken).toHaveBeenCalled();

    authMocks.getEmailFromToken.mockReturnValueOnce("user@bbva.com");
    authMocks.isEmailAllowed.mockReturnValueOnce(true);
    captured?.({ credential: "token" });
    expect(authMocks.storeToken).toHaveBeenCalledWith("token", "user@bbva.com");
  });
});
