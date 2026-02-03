/** Feature flags basados en variables de entorno (cliente). */

function parseBoolEnv(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined) return defaultValue;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "y", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "n", "off"].includes(normalized)) return false;
  return defaultValue;
}

export const INCIDENTS_FEATURE_ENABLED = parseBoolEnv(
  process.env.NEXT_PUBLIC_INCIDENTS_ENABLED,
  true
);
