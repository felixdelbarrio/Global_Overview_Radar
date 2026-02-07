type JwtPayload = {
  email?: string;
  exp?: number;
  name?: string;
};

const TOKEN_KEY = "gor-google-id-token";
const EMAIL_KEY = "gor-google-email";

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function hasStorage(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.localStorage !== "undefined" &&
    typeof window.localStorage.getItem === "function"
  );
}

function decodeBase64Url(value: string): string | null {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  if (isBrowser() && typeof window.atob === "function") {
    return window.atob(padded);
  }
  if (typeof Buffer !== "undefined") {
    return Buffer.from(padded, "base64").toString("utf-8");
  }
  return null;
}

export function parseJwtPayload(token: string): JwtPayload | null {
  const parts = token.split(".");
  if (parts.length < 2) return null;
  const decoded = decodeBase64Url(parts[1]);
  if (!decoded) return null;
  try {
    return JSON.parse(decoded) as JwtPayload;
  } catch {
    return null;
  }
}

export function getEmailFromToken(token: string): string | null {
  const payload = parseJwtPayload(token);
  return payload?.email ?? null;
}

export function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token);
  const exp = payload?.exp;
  if (!exp || typeof exp !== "number") return false;
  const now = Date.now() / 1000;
  return exp - 30 <= now;
}

export function getStoredToken(): string | null {
  if (!hasStorage()) return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getStoredEmail(): string | null {
  if (!hasStorage()) return null;
  return window.localStorage.getItem(EMAIL_KEY);
}

export function storeToken(token: string, email: string | null): void {
  if (!hasStorage()) return;
  window.localStorage.setItem(TOKEN_KEY, token);
  if (email) {
    window.localStorage.setItem(EMAIL_KEY, email);
  }
}

export function clearStoredToken(): void {
  if (!hasStorage()) return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(EMAIL_KEY);
}

export function readAllowedEmails(): string[] {
  const raw = process.env.NEXT_PUBLIC_ALLOWED_EMAILS || "";
  return raw
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

export function readAllowedDomains(): string[] {
  const raw = process.env.NEXT_PUBLIC_ALLOWED_DOMAINS || "";
  return raw
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

export function isEmailAllowed(email: string | null): boolean {
  if (!email) return false;
  const allowedEmails = readAllowedEmails();
  const allowedDomains = readAllowedDomains();
  if (!allowedEmails.length && !allowedDomains.length) return true;
  const normalized = email.toLowerCase();
  if (allowedEmails.includes(normalized)) return true;
  const domain = normalized.split("@")[1] || "";
  if (!domain) return false;
  return allowedDomains.includes(domain);
}
