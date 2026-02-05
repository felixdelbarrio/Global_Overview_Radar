import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const envPath = resolve(process.cwd(), ".env.local");
const examplePath = resolve(process.cwd(), ".env.local.example");

function parseKeys(contents) {
  const keys = new Set();
  for (const rawLine of contents.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    keys.add(line.slice(0, eq).trim());
  }
  return keys;
}

if (!existsSync(examplePath)) {
  process.exit(0);
}

const exampleContents = readFileSync(examplePath, "utf-8");

if (!existsSync(envPath)) {
  writeFileSync(envPath, exampleContents, "utf-8");
  process.exit(0);
}

const envContents = readFileSync(envPath, "utf-8");
const existingKeys = parseKeys(envContents);
const missingLines = [];

for (const rawLine of exampleContents.split(/\r?\n/)) {
  const line = rawLine.trim();
  if (!line || line.startsWith("#")) continue;
  const eq = line.indexOf("=");
  if (eq <= 0) continue;
  const key = line.slice(0, eq).trim();
  if (!existingKeys.has(key)) {
    missingLines.push(rawLine);
  }
}

if (missingLines.length > 0) {
  const suffix =
    `\n\n# Added automatically from .env.local.example\n` + missingLines.join("\n") + "\n";
  writeFileSync(envPath, envContents.replace(/\s*$/, "") + suffix, "utf-8");
}
