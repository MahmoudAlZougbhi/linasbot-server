/**
 * Canonical Testing Lab session helpers.
 * Chat View and Result Cards must share the same session key + transcript.
 */

export const TESTING_LAB_STORAGE_KEY = "testing_chat_sessions_v2";
export const DEFAULT_TEST_PHONE = "123456789";
export const MAX_CHAT_MESSAGES = 200;
export const MAX_LAB_TURNS = 100;

/**
 * @param {unknown} channel
 * @returns {"instagram" | "facebook" | "wa"}
 */
export function normalizeLabChannel(channel) {
  const value = typeof channel === "string" ? channel.trim().toLowerCase() : "";
  if (value === "instagram" || value === "facebook") return value;
  return "wa";
}

/**
 * @param {string} provider
 * @param {unknown} channel
 * @param {string} phone
 */
export function buildLabSessionKey(provider, channel, phone) {
  const normalizedProvider = (provider || "montymobile").trim() || "montymobile";
  const normalizedPhone = (phone || DEFAULT_TEST_PHONE).trim() || DEFAULT_TEST_PHONE;
  return `${normalizedProvider}:${normalizeLabChannel(channel)}:${normalizedPhone}`;
}

/** @returns {{ messages: TestingChatMessage[], turns: TestingTestResult[] }} */
export function emptyLabSession() {
  return { messages: [], turns: [] };
}

/**
 * @param {unknown} value
 * @returns {Record<string, { messages: TestingChatMessage[], turns: TestingTestResult[] }>}
 */
export function parseStoredLabSessions(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  /** @type {Record<string, { messages: TestingChatMessage[], turns: TestingTestResult[] }>} */
  const next = {};
  for (const [key, session] of Object.entries(value)) {
    if (!session || typeof session !== "object" || Array.isArray(session)) continue;
    const messages = Array.isArray(/** @type {{ messages?: unknown }} */ (session).messages)
      ? /** @type {TestingChatMessage[]} */ (/** @type {{ messages: TestingChatMessage[] }} */ (session).messages)
      : [];
    const turns = Array.isArray(/** @type {{ turns?: unknown }} */ (session).turns)
      ? /** @type {TestingTestResult[]} */ (/** @type {{ turns: TestingTestResult[] }} */ (session).turns)
      : [];
    next[key] = { messages, turns };
  }
  return next;
}

/** @returns {Record<string, { messages: TestingChatMessage[], turns: TestingTestResult[] }>} */
export function loadLabSessionsFromStorage() {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(TESTING_LAB_STORAGE_KEY);
    return parseStoredLabSessions(raw ? JSON.parse(raw) : {});
  } catch {
    return {};
  }
}

/**
 * @param {Record<string, { messages: TestingChatMessage[], turns: TestingTestResult[] }>} sessions
 */
export function persistLabSessions(sessions) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TESTING_LAB_STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // Ignore persistence errors so testing UI keeps working.
  }
}

/**
 * @param {string} output
 * @returns {string[]}
 */
export function splitBotOutputIntoMessages(output) {
  const normalizedOutput =
    typeof output === "string" && output.trim() ? output : "";
  if (!normalizedOutput) return [];
  const chunks = normalizedOutput
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean);
  return chunks.length ? chunks : [normalizedOutput];
}

/**
 * @param {Array<{ role?: string, type?: string, content?: string, timestamp?: string, success?: boolean }>} entries
 * @returns {TestingChatMessage[]}
 */
export function toChatMessages(entries) {
  const stamp = Date.now();
  return entries
    .filter((entry) => entry && entry.content)
    .map((entry, index) => ({
      id: `${stamp}-${index}-${Math.random().toString(36).slice(2, 8)}`,
      role: entry.role || "assistant",
      type: entry.type || "text",
      content: String(entry.content),
      timestamp: entry.timestamp || new Date().toLocaleTimeString(),
      success: entry.success !== false,
    }));
}

/**
 * @param {Record<string, { messages: TestingChatMessage[], turns: TestingTestResult[] }>} sessions
 * @param {string} sessionKey
 * @param {TestingChatMessage[]} messages
 */
export function appendMessagesToLabSessions(sessions, sessionKey, messages) {
  if (!messages.length) return sessions;
  const current = sessions[sessionKey] || emptyLabSession();
  return {
    ...sessions,
    [sessionKey]: {
      ...current,
      messages: [...current.messages, ...messages].slice(-MAX_CHAT_MESSAGES),
    },
  };
}

/**
 * @param {Record<string, { messages: TestingChatMessage[], turns: TestingTestResult[] }>} sessions
 * @param {string} sessionKey
 * @param {TestingTestResult} turn
 */
export function appendTurnToLabSessions(sessions, sessionKey, turn) {
  const current = sessions[sessionKey] || emptyLabSession();
  return {
    ...sessions,
    [sessionKey]: {
      ...current,
      turns: [turn, ...current.turns].slice(0, MAX_LAB_TURNS),
    },
  };
}

/**
 * @param {Record<string, { messages: TestingChatMessage[], turns: TestingTestResult[] }>} sessions
 * @param {string} sessionKey
 */
export function clearLabSession(sessions, sessionKey) {
  if (!sessions[sessionKey]) return sessions;
  const next = { ...sessions };
  delete next[sessionKey];
  return next;
}
