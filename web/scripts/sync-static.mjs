// Copy the Vite build into the Python package so the wheel ships the web app.
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = resolve(here, "../dist");
const target = resolve(here, "../../server/src/code_deck/static");

if (!existsSync(join(dist, "index.html"))) {
  console.error("dist/index.html missing — run `pnpm build` first");
  process.exit(1);
}
mkdirSync(target, { recursive: true });
for (const entry of readdirSync(target)) {
  if (entry !== ".gitkeep") rmSync(join(target, entry), { recursive: true, force: true });
}
cpSync(dist, target, { recursive: true });
writeFileSync(join(target, ".gitkeep"), "");
console.log(`synced ${dist} -> ${target}`);
