/**
 * Thin client for existing /api/guest-ai/* — no parallel guest system.
 */

const STORAGE_KEY = 'linas_guest_session_id';

/**
 * @typedef {Error & { status?: number; body?: unknown; code?: string }} GuestApiError
 */

function randomId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `guest-${crypto.randomUUID()}`;
  }
  return `guest-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function getOrCreateGuestSessionId() {
  try {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing && existing.length >= 8) return existing;
    const next = randomId();
    localStorage.setItem(STORAGE_KEY, next);
    return next;
  } catch {
    return randomId();
  }
}

/**
 * @param {Response} response
 */
async function parseJson(response) {
  const text = await response.text();
  if (!text) return {};
  return JSON.parse(text);
}

/**
 * @param {string} message
 * @param {number} [status]
 * @param {unknown} [body]
 * @param {string} [code]
 * @returns {GuestApiError}
 */
function guestApiError(message, status, body, code) {
  /** @type {GuestApiError} */
  const err = new Error(message);
  if (status != null) err.status = status;
  if (body !== undefined) err.body = body;
  if (code) err.code = code;
  return err;
}

/**
 * @param {unknown} body
 */
function detailCode(body) {
  if (!body || typeof body !== 'object') return null;
  const detail = /** @type {{ detail?: unknown }} */ (body).detail;
  if (!detail || typeof detail !== 'object') return null;
  const row = /** @type {{ code?: unknown; error?: unknown }} */ (detail);
  if (typeof row.code === 'string') return row.code;
  if (typeof row.error === 'string') return row.error;
  return null;
}

/**
 * @param {string} guestSessionId
 * @param {string} [language]
 */
export async function ensureGuestSession(guestSessionId, language = 'en') {
  const response = await fetch('/api/guest-ai/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ guest_session_id: guestSessionId, language }),
  });
  const body = await parseJson(response);
  if (!response.ok) {
    throw guestApiError('Guest session failed', response.status, body);
  }
  return body.session;
}

/**
 * @param {string} guestSessionId
 * @param {string} content
 * @param {string} [language]
 */
export async function sendGuestMessage(guestSessionId, content, language = 'en') {
  const response = await fetch('/api/guest-ai/session/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ guest_session_id: guestSessionId, content, language }),
  });
  const body = await parseJson(response);
  if (response.status === 400) {
    const code = detailCode(body) || 'rejected';
    throw guestApiError(code, 400, body, code);
  }
  if (!response.ok) {
    throw guestApiError('Guest message failed', response.status, body);
  }
  if (body?.success === false && body?.code === 'GUEST_QUESTION_LIMIT') {
    return { ok: false, session: body.session, gateMessages: body.message };
  }
  return { ok: true, session: body.session, message: body.message };
}
