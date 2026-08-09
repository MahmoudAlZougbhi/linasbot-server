#!/usr/bin/env node
/**
 * Fail if tracked mobile source/config embeds provider or server secrets.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("../mobile/linas-ai", import.meta.url).pathname;
const SKIP = new Set(["node_modules", "android", "ios", ".expo", "dist"]);

const PATTERNS = [
  /sk-[A-Za-z0-9]{20,}/,
  /OPENAI_API_KEY\s*[:=]/,
  /META_APP_SECRET\s*[:=]/,
  /DASHBOARD_AUTH_SECRET\s*[:=]/,
  /STRIPE_SECRET_KEY\s*[:=]/,
  /BEGIN (RSA |EC )?PRIVATE KEY/,
  /firebase_data\.json/,
  /AIza[0-9A-Za-z_-]{30,}/,
];

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name) || name.startsWith(".")) continue;
    const path = join(dir, name);
    const st = statSync(path);
    if (st.isDirectory()) walk(path, out);
    else if (/\.(ts|tsx|js|jsx|json|env|md)$/.test(name)) out.push(path);
  }
  return out;
}

const files = walk(ROOT);
const hits = [];
for (const file of files) {
  const text = readFileSync(file, "utf8");
  for (const re of PATTERNS) {
    if (re.test(text)) {
      // Allow documenting env var names in README without values.
      if (file.endsWith("README.md") && /OPENAI_API_KEY|META_APP_SECRET/.test(re.source)) {
        continue;
      }
      hits.push(`${relative(ROOT, file)} matches ${re}`);
    }
  }
}

if (hits.length) {
  console.error("Mobile secret scan failed:");
  for (const h of hits) console.error(" -", h);
  process.exit(1);
}
console.log(`Mobile secret scan OK (${files.length} files).`);
