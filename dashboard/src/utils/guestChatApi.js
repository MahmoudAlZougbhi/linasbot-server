/**
 * Thin client for existing /api/guest-ai/* — no parallel guest system.
 */

const STORAGE_KEY = 'linas_guest_session_id';

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

async function parseJson(response) {
  const text = await response.text();
  if (!text) return {};
  return JSON.parse(text);
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
    const err = new Error('Guest session failed');
    err.status = response.status;
    err.body = body;
    throw err;
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
    const err = new Error('word_limit');
    err.status = 400;
    err.body = body;
    throw err;
  }
  if (!response.ok) {
    const err = new Error('Guest message failed');
    err.status = response.status;
    err.body = body;
    throw err;
  }
  if (body?.success === false && body?.code === 'GUEST_QUESTION_LIMIT') {
    return { ok: false, session: body.session, gateMessages: body.message };
  }
  return { ok: true, session: body.session, message: body.message };
}

export function countWords(text) {
  return (text || '').trim().split(/\s+/).filter(Boolean).length;
}
