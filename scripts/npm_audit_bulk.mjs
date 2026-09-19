/**
 * Production-tree audit via the registry bulk advisory API.
 * Used when npm CLI still falls back to the retired quick-audit endpoint.
 */
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";

const BULK_URL = "https://registry.npmjs.org/-/npm/v1/security/advisories/bulk";
const SEVERITIES = ["info", "low", "moderate", "high", "critical"];

export function productionVersionsFromLock(lockPath) {
  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  const payload = {};
  for (const [key, meta] of Object.entries(lock.packages || {})) {
    if (!key || !meta || meta.dev === true || typeof meta.version !== "string") continue;
    const parts = key.split("node_modules/");
    const name = String(meta.name || parts[parts.length - 1] || "").trim();
    if (!name) continue;
    const versions = payload[name] || [];
    if (!versions.includes(meta.version)) versions.push(meta.version);
    payload[name] = versions;
  }
  return payload;
}

function decodeBody(buf) {
  if (buf.length >= 2 && buf[0] === 0x1f && buf[1] === 0x8b) {
    return gunzipSync(buf).toString("utf8");
  }
  return buf.toString("utf8");
}

export async function fetchBulkAdvisories(payload, { retries = 3 } = {}) {
  let lastErr = "bulk advisory request failed";
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      const res = await fetch(BULK_URL, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          accept: "application/json",
          "user-agent": "linas-npm-audit-gate/1",
        },
        body: JSON.stringify(payload),
      });
      const text = decodeBody(Buffer.from(await res.arrayBuffer()));
      if (!res.ok) {
        lastErr = `bulk HTTP ${res.status}: ${text.slice(0, 200)}`;
      } else {
        const parsed = JSON.parse(text);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
        lastErr = "bulk advisory response was not an object";
      }
    } catch (err) {
      lastErr = err instanceof Error ? err.message : String(err);
    }
    await new Promise((resolve) => setTimeout(resolve, 400 * attempt));
  }
  throw new Error(lastErr);
}

function rank(severity) {
  const idx = SEVERITIES.indexOf(severity);
  return idx < 0 ? 0 : idx;
}

export function bulkToAuditV2(bulk) {
  const vulnerabilities = {};
  const counts = { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 };
  for (const [name, rows] of Object.entries(bulk || {})) {
    if (!Array.isArray(rows) || !rows.length) continue;
    let worst = "info";
    const via = [];
    const ranges = [];
    for (const row of rows) {
      if (!row || typeof row !== "object") continue;
      const severity = String(row.severity || "info");
      if (rank(severity) > rank(worst)) worst = severity;
      via.push({
        source: row.url || row.id || name,
        url: row.url,
        title: row.title,
        ghsa: row.github_advisory_id || row.id,
      });
      if (row.vulnerable_versions) ranges.push(String(row.vulnerable_versions));
    }
    if (!via.length) continue;
    vulnerabilities[name] = { name, severity: worst, via, range: ranges.join(" || ") };
    if (counts[worst] !== undefined) counts[worst] += 1;
    counts.total += 1;
  }
  return {
    auditReportVersion: 2,
    metadata: { vulnerabilities: counts },
    vulnerabilities,
  };
}
