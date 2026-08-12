/** Redact PII from ActivityFlow entries before "Show technical JSON". */

const REDACTED = "[REDACTED]";

/** @type {ReadonlySet<string>} */
const PII_KEYS = new Set([
  "user_phone",
  "user_phone_masked",
  "phone",
  "phone_number",
  "user_id",
  "user_id_masked",
  "user_name",
  "user_message",
  "bot_to_user",
  "ai_raw_response",
  "bot_sent_to_ai_full",
  "customer_context_sent",
  "ai_query_summary",
  "message",
  "content",
  "text",
  "body",
  "raw",
  "raw_payload",
  "raw_cm",
  "cm_raw",
  "prompt",
  "completion",
]);

/**
 * @param {string} key
 * @returns {boolean}
 */
function isPiiKey(key) {
  const keyLower = String(key || "").toLowerCase();
  return PII_KEYS.has(keyLower) || keyLower.endsWith("_phone") || keyLower.endsWith("_message");
}

/**
 * @param {unknown} value
 * @param {string} [key]
 * @returns {unknown}
 */
function redactValue(value, key = "") {
  if (value == null) return value;
  if (isPiiKey(key)) {
    return REDACTED;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactValue(item, key));
  }
  if (typeof value === "object") {
    /** @type {Record<string, unknown>} */
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      const kl = k.toLowerCase();
      if (kl === "cm_diagnostics" || kl === "cm_raw" || kl === "raw_cm_payload") {
        out[k] = redactCmDiagnostics(v);
        continue;
      }
      if (kl === "flow_steps" && Array.isArray(v)) {
        out[k] = v.map((step) => redactFlowStep(step));
        continue;
      }
      out[k] = redactValue(v, k);
    }
    return out;
  }
  return value;
}

/**
 * Keep CM diagnostic structure without raw retrieved payloads / message bodies.
 * @param {unknown} cm
 * @returns {unknown}
 */
function redactCmDiagnostics(cm) {
  if (!cm || typeof cm !== "object" || Array.isArray(cm)) {
    return REDACTED;
  }
  const src = /** @type {Record<string, unknown>} */ (cm);
  const sourceIds = Array.isArray(src.source_ids) ? src.source_ids : [];
  const retrieved = Array.isArray(src.retrieved_sources) ? src.retrieved_sources : [];
  return {
    reason: src.reason ?? null,
    content_version_id: src.content_version_id ?? null,
    source_ids_count: sourceIds.length,
    retrieved_sources_count: retrieved.length,
    retrieved_source_ids: retrieved
      .slice(0, 20)
      .map((s) => (s && typeof s === "object" ? String(/** @type {Record<string, unknown>} */ (s).source_id || "") : ""))
      .filter(Boolean),
    raw_payload: REDACTED,
  };
}

/**
 * @param {unknown} step
 * @returns {Record<string, unknown> | unknown}
 */
function redactFlowStep(step) {
  if (!step || typeof step !== "object" || Array.isArray(step)) {
    return step;
  }
  const s = /** @type {Record<string, unknown>} */ (step);
  return {
    step: s.step ?? null,
    title: s.title ?? null,
    event_type: s.event_type ?? null,
    status: s.status ?? null,
    tokens: s.tokens ?? null,
    model: s.model ?? null,
    cost_usd: s.cost_usd ?? null,
    duration_ms: s.duration_ms ?? null,
    content: REDACTED,
    metadata: s.metadata != null && typeof s.metadata === "object"
      ? { keys: Object.keys(/** @type {object} */ (s.metadata)) }
      : undefined,
  };
}

/**
 * Deep-clone entry with phones, message bodies, user ids, and raw CM payloads redacted.
 * Keeps non-PII diagnostic fields (source, channel, cost, model, outcome, etc.).
 * @param {ActivityFlowEntry | Record<string, unknown> | null | undefined} entry
 * @returns {Record<string, unknown>}
 */
export function redactActivityFlowEntryForJson(entry) {
  if (!entry || typeof entry !== "object") {
    return {};
  }
  return /** @type {Record<string, unknown>} */ (redactValue(entry));
}

export { REDACTED };
