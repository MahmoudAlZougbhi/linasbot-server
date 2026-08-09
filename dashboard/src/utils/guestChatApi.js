/**
 * Thin client for existing /api/guest-ai/* — no parallel guest system.
 */

const STORAGE_KEY = 'linas_guest_session_id';

/**
 * @typedef {Error & { status?: number; body?: unknown }} GuestApiError
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
 * @returns {GuestApiError}
 */
function guestApiError(message, status, body) {
  /** @type {GuestApiError} */
  const err = new Error(message);
  if (status != null) err.status = status;
  if (body !== undefined) err.body = body;
  return err;
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
    throw guestApiError('word_limit', 400, body);
  }
  if (!response.ok) {
    throw guestApiError('Guest message failed', response.status, body);
  }
  if (body?.success === false && body?.code === 'GUEST_QUESTION_LIMIT') {
    return { ok: false, session: body.session, gateMessages: body.message };
  }
  return { ok: true, session: body.session, message: body.message };
}

/**
 * @param {string} text
 */
export function countWords(text) {
  return (text || '').trim().split(/\s+/).filter(Boolean).length;
}
