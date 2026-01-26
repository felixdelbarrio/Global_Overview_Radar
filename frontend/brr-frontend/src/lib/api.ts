export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

export async function apiGet<T>(path: string): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  const res = await fetch(url, { cache: "no-store" });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} failed: ${res.status}${text ? ` — ${text}` : ""}`);
  }

  return (await res.json()) as T;
}