import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const envPath = resolve(process.cwd(), ".env.local");
const examplePath = resolve(process.cwd(), ".env.local.example");

if (!existsSync(envPath) && existsSync(examplePath)) {
  const contents = readFileSync(examplePath, "utf-8");
  writeFileSync(envPath, contents, "utf-8");
}
