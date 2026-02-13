export const MARKET_REPUTATION_SOURCES = [
  "appstore",
  "google_play",
  "downdetector",
] as const;

export const PRESS_REPUTATION_SOURCES = [
  "news",
  "newsapi",
  "gdelt",
  "guardian",
  "forums",
  "blogs",
  "trustpilot",
  "google_reviews",
  "youtube",
  "reddit",
  "twitter",
] as const;

export const MARKET_REPUTATION_SOURCE_SET = new Set<string>(MARKET_REPUTATION_SOURCES);
export const PRESS_REPUTATION_SOURCE_SET = new Set<string>(PRESS_REPUTATION_SOURCES);

export function hasMarketSourcesEnabled(sources: string[]): boolean {
  return sources.some((source) => MARKET_REPUTATION_SOURCE_SET.has(source));
}

export function hasPressSourcesEnabled(sources: string[]): boolean {
  return sources.some((source) => PRESS_REPUTATION_SOURCE_SET.has(source));
}

export function filterSourcesByScope(
  sources: string[],
  scope: "all" | "markets" | "press",
): string[] {
  if (scope === "all") return sources;
  const set =
    scope === "markets" ? MARKET_REPUTATION_SOURCE_SET : PRESS_REPUTATION_SOURCE_SET;
  return sources.filter((source) => set.has(source));
}
