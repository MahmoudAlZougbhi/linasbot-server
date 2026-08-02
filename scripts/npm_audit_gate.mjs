#!/usr/bin/env node
/**
 * Production dependency audit gate.
 *
 * Allowed exception (narrow):
 *   Advisory: GHSA-qwww-vcr4-c8h2 (React Router RSC Mode CSRF)
 *   Packages: react-router, react-router-dom
 *   Versions: exactly installed >=7.18.2 (patched Declarative Mode) OR >=8.3.0
 *   Architecture proof: dashboard/src/App.jsx must use Declarative Mode and must
 *     NOT contain RSC APIs. package.json must pin react-router-dom to a patched version.
 *
 * This is NOT a general high-severity bypass. Any other high/critical finding fails.
 * Exception auto-invalidates if version drops below patched floor or App.jsx uses RSC.
 */
import { execSync } from "node:child_process";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ADVISORY_ID = "GHSA-qwww-vcr4-c8h2";
const PATCHED_FLOOR_7 = "7.18.2";
const PATCHED_FLOOR_8 = "8.3.0";

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

function isPatchedRouterVersion(ver) {
  if (!ver) return false;
  if (cmp(ver, "8.0.0") >= 0) return cmp(ver, PATCHED_FLOOR_8) >= 0;
  return cmp(ver, PATCHED_FLOOR_7) >= 0;
}

function packageJsonPinsPatchedRouter() {
  const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
  const pinned = String(pkg.dependencies?.["react-router-dom"] || "");
  // Accept exact "7.18.2" or ">=7.18.2" style pins; reject ranges that allow unpatched.
  if (!pinned) return false;
  if (pinned === PATCHED_FLOOR_7 || pinned === PATCHED_FLOOR_8) return true;
  if (pinned.startsWith("^") || pinned.startsWith("~")) {
    const base = pinned.slice(1);
    return isPatchedRouterVersion(base);
  }
  return isPatchedRouterVersion(pinned.replace(/^[^0-9]*/, ""));
}

function appIsDeclarativeNonRsc() {
  const appSrc = readFileSync(join(root, "src/App.jsx"), "utf8");
  const usesBrowserRouter = /BrowserRouter|HashRouter|MemoryRouter/.test(appSrc);
  const usesRsc =
    /unstable_RSC|createFromReadableStream|react-server-dom|RSCPayload/i.test(appSrc);
  return usesBrowserRouter && !usesRsc;
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

const auditMeta = report?.metadata?.vulnerabilities;
const completeSeverityCounts =
  auditMeta &&
  ["info", "low", "moderate", "high", "critical", "total"].every(
    (severity) => Number.isInteger(auditMeta[severity]) && auditMeta[severity] >= 0
  );
if (report?.error || report?.auditReportVersion !== 2 || !completeSeverityCounts) {
  console.error("npm audit returned an incomplete or error report; refusing to pass");
  process.exit(1);
}

const vulns = report.vulnerabilities || {};
const allow = [];
const block = [];
const architectureOk = appIsDeclarativeNonRsc();
const pinOk = packageJsonPinsPatchedRouter();
const routerVer = versionOf("react-router-dom") || versionOf("react-router");
const routerExceptionEligible =
  isPatchedRouterVersion(routerVer) && architectureOk && pinOk;

/**
 * True when this finding is exactly GHSA-qwww-vcr4-c8h2 on react-router /
 * react-router-dom (direct advisory entry or npm's "via react-router" edge).
 */
function isGhsaQwwwRouterFinding(name, via) {
  const isRouterPkg = name === "react-router" || name === "react-router-dom";
  if (!isRouterPkg) return false;
  const viaBlob = JSON.stringify(via);
  if (
    viaBlob.includes(ADVISORY_ID) ||
    /RSC Mode CSRF/i.test(viaBlob) ||
    via.some(
      (x) =>
        typeof x === "object" &&
        x &&
        (String(x.source || "").includes(ADVISORY_ID) ||
          String(x.url || "").includes(ADVISORY_ID) ||
          /RSC Mode CSRF/i.test(String(x.title || "")))
    )
  ) {
    return true;
  }
  // react-router-dom often reports only via: ["react-router"] with no advisory object.
  // Allow that edge only when the dependency chain is exclusively react-router and
  // the installed react-router package itself carries this advisory (or is clean).
  if (
    name === "react-router-dom" &&
    via.length > 0 &&
    via.every((x) => x === "react-router")
  ) {
    const parent = vulns["react-router"];
    if (!parent) return routerExceptionEligible;
    const parentVia = Array.isArray(parent.via) ? parent.via : [];
    return isGhsaQwwwRouterFinding("react-router", parentVia);
  }
  return false;
}

for (const [name, v] of Object.entries(vulns)) {
  const sev = v.severity;
  if (!["high", "critical"].includes(sev)) continue;

  const via = Array.isArray(v.via) ? v.via : [];
  const viaBlob = JSON.stringify(via);

  if (isGhsaQwwwRouterFinding(name, via) && routerExceptionEligible) {
    allow.push({
      advisory: ADVISORY_ID,
      name,
      severity: sev,
      installed: versionOf(name) || routerVer,
      packageJsonPinOk: pinOk,
      declarativeNonRsc: architectureOk,
      evidence:
        "Exception limited to GHSA-qwww-vcr4-c8h2. Patched Declarative floor is react-router(-dom) >=7.18.2 (or >=8.3.0). npm advisory range still mis-lists 7.18.2. App.jsx uses BrowserRouter/HashRouter/MemoryRouter and has no RSC APIs. Auto-invalidates if pin/version drops or App.jsx adopts RSC.",
    });
    continue;
  }

  block.push({
    name,
    sev,
    range: v.range,
    via: viaBlob.slice(0, 240),
  });
}

const meta = auditMeta;
console.log("npm audit severity counts:", JSON.stringify(meta));
console.log("allowed documented findings:", JSON.stringify(allow, null, 2));
if (!architectureOk) {
  console.error("Architecture proof failed: App.jsx must be Declarative non-RSC");
  process.exit(1);
}
if (block.length) {
  console.error("blocking findings:", JSON.stringify(block, null, 2));
  process.exit(1);
}
console.log("npm audit gate passed");
process.exit(0);
