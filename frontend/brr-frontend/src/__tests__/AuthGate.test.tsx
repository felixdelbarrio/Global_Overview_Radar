/** Tests del componente AuthGate. */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type GoogleIdApi = {
  disableAutoSelect?: () => void;
  initialize?: (config: {
    client_id?: string;
    ux_mode?: string;
    login_uri?: string;
  }) => void;
  renderButton?: () => void;
};
type GoogleAccounts = { id?: GoogleIdApi };
type GoogleStub = { accounts?: GoogleAccounts };
type WindowWithGoogle = Window & { google?: GoogleStub };

const setGoogle = (value?: GoogleStub) => {
  (window as WindowWithGoogle).google = value;
};

const replaceMock = vi.fn();
const usePathnameMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => usePathnameMock(),
}));

const ScriptMock = ({ onLoad }: { onLoad?: () => void }) => {
  React.useEffect(() => {
    onLoad?.();
  }, [onLoad]);
  return null;
};

vi.mock("next/script", () => ({
  default: ScriptMock,
}));

const authMocks = {
  clearStoredToken: vi.fn(),
  getEmailFromToken: vi.fn(),
  getStoredToken: vi.fn(),
  isTokenExpired: vi.fn(),
  storeToken: vi.fn(),
};

vi.mock("@/lib/auth", () => authMocks);

const apiMocks = {
  apiGet: vi.fn(),
};

vi.mock("@/lib/api", () => apiMocks);

const originalEnv = { ...process.env };

const loadAuthGate = async (env: Record<string, string | undefined>) => {
  vi.resetModules();
  process.env = { ...originalEnv, ...env };
  const mod = await import("@/components/AuthGate");
  const resolvedClientId = process.env.AUTH_GOOGLE_CLIENT_ID ?? "";
  const WrappedAuthGate = ({ children }: { children: React.ReactNode }) => (
    <mod.AuthGate clientId={resolvedClientId}>{children}</mod.AuthGate>
  );
  WrappedAuthGate.displayName = "WrappedAuthGate";
  return WrappedAuthGate;
};

beforeEach(() => {
  replaceMock.mockReset();
  usePathnameMock.mockReturnValue("/");
  authMocks.clearStoredToken.mockReset();
  authMocks.getEmailFromToken.mockReset();
  authMocks.getStoredToken.mockReset();
  authMocks.isTokenExpired.mockReset();
  authMocks.storeToken.mockReset();
  authMocks.isTokenExpired.mockReturnValue(false);
  authMocks.getEmailFromToken.mockReturnValue("user@bbva.com");
  authMocks.getStoredToken.mockReturnValue(null);
  apiMocks.apiGet.mockReset();
  apiMocks.apiGet.mockResolvedValue({ email: "user@bbva.com" });
  setGoogle(undefined);
  window.history.pushState({}, "", "/");
});

afterEach(() => {
  process.env = { ...originalEnv };
});

describe("AuthGate", () => {
  it("renders children when auth is disabled", async () => {
    const AuthGate = await loadAuthGate({
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    expect(screen.getByText("Contenido")).toBeInTheDocument();
  });

  it("renders children when login bypass is enabled", async () => {
    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "false",
      AUTH_GOOGLE_CLIENT_ID: "",
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
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    expect(
      screen.getByText("Falta configurar `AUTH_GOOGLE_CLIENT_ID`.")
    ).toBeInTheDocument();
  });

  it("shows login screen when unauthenticated on /login", async () => {
    usePathnameMock.mockReturnValue("/login");
    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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
    setGoogle({
      accounts: { id: { disableAutoSelect, initialize } },
    });

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
    });

    render(
      <AuthGate>
        <div>Contenido</div>
      </AuthGate>
    );

    await waitFor(() => {
      expect(screen.getByText("Conectado: user@bbva.com")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Salir" }));
    expect(authMocks.clearStoredToken).toHaveBeenCalled();
    expect(disableAutoSelect).toHaveBeenCalled();
  });

  it("sanitizes next param when redirecting from login", async () => {
    usePathnameMock.mockReturnValue("/login");
    authMocks.getStoredToken.mockReturnValue("token");
    window.history.pushState({}, "", "/login?next=//evil.com");

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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

  it("initializes google in redirect mode", async () => {
    usePathnameMock.mockReturnValue("/login");
    authMocks.getStoredToken.mockReturnValue(null);

    const initialize = vi.fn();
    const renderButton = vi.fn();
    setGoogle({
      accounts: { id: { initialize, renderButton } },
    });

    const AuthGate = await loadAuthGate({
      NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED: "true",
      AUTH_GOOGLE_CLIENT_ID: "test-client",
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

    const config = initialize.mock.calls[0]?.[0] ?? {};
    expect(config.client_id).toBe("test-client");
    expect(config.ux_mode).toBe("redirect");
    expect(config.login_uri).toBe("http://localhost:3000/login/callback");
  });
});
