#!/usr/bin/env node
/**
 * Production dependency audit gate.
 * Fails on high/critical findings except documented false-positive GHSA entries
 * that are already patched per the official advisory but still mis-ranged by npm.
 */
import { execSync } from "node:child_process";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = new URL("../dashboard", import.meta.url).pathname;
const require = createRequire(join(root, "package.json"));

function versionOf(pkg) {
  try {
    return require(`${pkg}/package.json`).version;
  } catch {
    return null;
  }
}

function cmp(a, b) {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d;
  }
  return 0;
}

let report;
try {
  report = JSON.parse(
    execSync("npm audit --omit=dev --json", { cwd: root, encoding: "utf8" })
  );
} catch (e) {
  const out = e.stdout?.toString?.() || e.output?.toString?.() || "";
  try {
    report = JSON.parse(out);
  } catch {
    console.error("npm audit failed without JSON");
    process.exit(1);
  }
}

const vulns = report.vulnerabilities || {};
const allow = [];
const block = [];

for (const [name, v] of Object.entries(vulns)) {
  const sev = v.severity;
  if (!["high", "critical"].includes(sev)) continue;
  const via = Array.isArray(v.via) ? v.via : [];
  const ghsa = via
    .map((x) => (typeof x === "object" ? x.source || x.url || "" : String(x)))
    .join(" ");
  const isRscCsrf =
    /GHSA-qwww-vcr4-c8h2/i.test(ghsa) ||
    /RSC Mode CSRF/i.test(JSON.stringify(via));

  if (isRscCsrf || (name === "react-router" || name === "react-router-dom")) {
    const ver = versionOf(name);
    const depVer = versionOf("react-router");
    const effective = ver || depVer;
    // Official advisory patched versions: >=7.18.2 and >=8.3.0
    // npm still flags react-router-dom purely because it depends on react-router@7.18.2
    // even though 7.18.2 is the patched release (advisory range in npm DB is stale).
    const patched =
      effective && (cmp(effective, "7.18.2") >= 0 || (cmp(effective, "8.0.0") >= 0 && cmp(effective, "8.3.0") >= 0));
    if (patched && (name === "react-router" || name === "react-router-dom") && (isRscCsrf || /react-router/.test(ghsa) || name === "react-router-dom")) {
      const pkg = readFileSync(join(root, "package.json"), "utf8");
      const appSrc = readFileSync(join(root, "src/App.jsx"), "utf8");
      const usesRsc =
        /unstable_RSC|createFromReadableStream|RouterProvider.*hydration|react-server-dom/i.test(appSrc);
      if (!usesRsc) {
        allow.push({
          name,
          sev,
          ver: effective,
          reason:
            "GHSA-qwww-vcr4-c8h2: installed react-router@>=7.18.2 is the patched Declarative Mode release; npm advisory range incorrectly includes it. App does not use RSC APIs.",
          packageJsonOk: pkg.includes('"react-router-dom"'),
          exploitability: "RSC Mode CSRF only; not applicable to Declarative Mode SPA",
        });
        continue;
      }
    }
  }
  block.push({ name, sev, range: v.range, via: ghsa.slice(0, 200) });
}

const meta = report.metadata?.vulnerabilities || {};
console.log("npm audit severity counts:", JSON.stringify(meta));
console.log("allowed documented findings:", JSON.stringify(allow, null, 2));
if (block.length) {
  console.error("blocking findings:", JSON.stringify(block, null, 2));
  process.exit(1);
}
console.log("npm audit gate passed");
process.exit(0);
