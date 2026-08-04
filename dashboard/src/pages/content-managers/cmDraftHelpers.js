/**
 * Shared helpers for Content Management draft forms (no JSON owner workflow).
 */

/**
 * @param {unknown} value
 * @returns {Record<string, unknown>}
 */
export function asRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? /** @type {Record<string, unknown>} */ (value)
    : {};
}

/**
 * @param {unknown} value
 * @returns {Array<Record<string, unknown>>}
 */
export function asRecordList(value) {
  return Array.isArray(value) ? /** @type {Array<Record<string, unknown>>} */ (value) : [];
}

/** @returns {{ en: string, ar: string, fr: string, franco: string }} */
export function emptyLabels() {
  return { en: "", ar: "", fr: "", franco: "" };
}

/**
 * @param {unknown} labels
 * @returns {string}
 */
export function primaryLabel(labels) {
  const rec = asRecord(labels);
  for (const key of ["en", "ar", "fr", "franco"]) {
    const v = rec[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return "";
}

/**
 * @param {string} prefix
 * @returns {string}
 */
export function newId(prefix) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * @param {string | null | undefined} status
 * @returns {string}
 */
export function statusBadgeClass(status) {
  switch (String(status || "active")) {
    case "draft":
      return "bg-amber-100 text-amber-800";
    case "archived":
      return "bg-slate-200 text-slate-700";
    case "restricted":
      return "bg-rose-100 text-rose-800";
    case "active":
    default:
      return "bg-emerald-100 text-emerald-800";
  }
}
