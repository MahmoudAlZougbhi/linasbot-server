/** Strip CM remigrate provenance headers from owner-facing text. */
const PROVENANCE_PREFIX = "--- redistributed from ";
const PROVENANCE_HEADER_RE = /--- redistributed from [\s\S]*? ---[ \t]*\n?/g;

const AI_BASICS_TEXT_FIELDS = [
  "greeting_behavior",
  "short_introduction",
  "identity_summary",
  "advanced_instructions",
];

/**
 * @param {unknown} text
 * @returns {string}
 */
export function stripProvenanceHeaders(text) {
  const raw = text == null ? "" : String(text);
  if (!raw.includes(PROVENANCE_PREFIX)) return raw;
  return raw.replace(PROVENANCE_HEADER_RE, "").trim();
}

/**
 * @param {string} section
 * @param {Record<string, unknown>} payload
 * @returns {Record<string, unknown>}
 */
export function sanitizeCmSectionPayload(section, payload) {
  const name = String(section || "").trim().replace(/-/g, "_");
  const out = { ...payload };
  if (name === "ai_basics") {
    for (const key of AI_BASICS_TEXT_FIELDS) {
      if (typeof out[key] === "string") {
        out[key] = stripProvenanceHeaders(out[key]);
      }
    }
  } else if (name === "style" && typeof out.style_body === "string") {
    out.style_body = stripProvenanceHeaders(out.style_body);
  }
  return out;
}
