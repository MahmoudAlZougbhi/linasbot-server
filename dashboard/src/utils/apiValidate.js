/**
 * Runtime validators for unknown API / JSON payloads.
 * Use before treating response bodies as domain objects.
 */

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
export function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * @param {unknown} value
 * @returns {value is { success: boolean } & Record<string, unknown>}
 */
export function isApiResult(value) {
  return isPlainObject(value) && typeof value.success === "boolean";
}

/**
 * @param {unknown} value
 * @returns {string}
 */
export function errorMessage(value) {
  if (value instanceof Error) return value.message;
  if (typeof value === "string") return value;
  if (isPlainObject(value) && typeof value.message === "string") return value.message;
  if (isPlainObject(value) && typeof value.error === "string") return value.error;
  try {
    return JSON.stringify(value);
  } catch {
    return "Unknown error";
  }
}

/**
 * @param {unknown} value
 * @returns {value is AuthUser}
 */
export function isAuthUser(value) {
  if (!isPlainObject(value)) return false;
  return typeof value.email === "string" || typeof value.id === "string";
}

/**
 * Parse JSON from a fetch Response; return unknown for callers to narrow.
 * @param {Response} response
 * @returns {Promise<unknown>}
 */
export async function readJsonUnknown(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { success: false, error: "Invalid JSON response", raw: text.slice(0, 200) };
  }
}

/**
 * @param {unknown} data
 * @returns {data is { success: true, user: Record<string, unknown> }}
 */
export function isAuthSuccess(data) {
  return isApiResult(data) && data.success === true && isPlainObject(data.user);
}

/**
 * @param {unknown} value
 * @returns {Record<string, unknown>}
 */
export function recordOrEmpty(value) {
  return isPlainObject(value) ? value : {};
}

/**
 * @param {unknown} value
 * @returns {unknown[]}
 */
export function arrayOrEmpty(value) {
  return Array.isArray(value) ? value : [];
}

/**
 * @param {unknown} value
 * @returns {number}
 */
export function metricNumber(value) {
  if (typeof value === "number" && !Number.isNaN(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return 0;
}

/**
 * @param {unknown} value
 * @returns {string}
 */
export function metricString(value) {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

/**
 * @param {unknown} value
 * @returns {Array<Record<string, unknown>>}
 */
export function metricRows(value) {
  if (!Array.isArray(value)) return [];
  return value.filter(isPlainObject);
}

/**
 * @param {unknown} value
 * @returns {Record<string, unknown>}
 */
export function metricRecord(value) {
  return isPlainObject(value) ? value : {};
}

/**
 * @param {unknown} value
 * @returns {Array<Record<string, unknown>>}
 */
export function recordArray(value) {
  return arrayOrEmpty(value).filter(isPlainObject);
}

/**
 * @param {unknown} value
 * @returns {string[]}
 */
export function metricStringArray(value) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => metricString(item)).filter((item) => item.length > 0);
}

/**
 * @param {unknown} error
 * @returns {error is AxiosLikeError}
 */
export function isAxiosLikeError(error) {
  return (
    typeof error === "object" &&
    error !== null &&
    ("code" in error || "message" in error || "response" in error)
  );
}

/**
 * @param {unknown} error
 * @returns {string | undefined}
 */
export function getAxiosErrorCode(error) {
  if (isAxiosLikeError(error) && typeof error.code === "string") {
    return error.code;
  }
  return undefined;
}

/**
 * @param {unknown} error
 * @returns {string | undefined}
 */
export function getAxiosResponseDetail(error) {
  if (!isAxiosLikeError(error) || !isPlainObject(error.response?.data)) {
    return undefined;
  }
  const data = error.response.data;
  if (typeof data.detail === "string") return data.detail;
  if (typeof data.error === "string") return data.error;
  if (typeof data.message === "string") return data.message;
  return undefined;
}
