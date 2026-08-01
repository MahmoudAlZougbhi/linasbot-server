import { getApiAbsoluteBaseUrl } from "./apiBaseUrl";
import { csrfHeaders } from "./csrf";

/** @param {string} url @param {RequestInit} [options] */
const liveChatFetch = (url, options = {}) => {
  /** @type {Record<string, string>} */
  const headers = {};
  if (options.headers) {
    if (options.headers instanceof Headers) {
      options.headers.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (Array.isArray(options.headers)) {
      options.headers.forEach(([key, value]) => {
        headers[key] = value;
      });
    } else {
      Object.assign(headers, options.headers);
    }
  }
  Object.assign(headers, csrfHeaders());
  return fetch(url, {
    credentials: "include",
    ...options,
    headers,
  });
};

/** @param {LiveChatMessage[]} [messages] */
export const normalizeConversationMessages = (messages = []) =>
  [...messages].sort((left, right) => {
    const leftTs = new Date(left?.timestamp || 0).getTime();
    const rightTs = new Date(right?.timestamp || 0).getTime();
    return leftTs - rightTs;
  });

/**
 * @param {{
 *   userId: string;
 *   conversationId: string;
 *   days?: number;
 *   before?: string | null;
 *   day_window?: number;
 *   limit?: number;
 *   timeoutMs?: number;
 * }} params
 */
export const fetchLiveChatConversationMessages = async ({
  userId,
  conversationId,
  days = 0,
  before = null,
  day_window = 0,
  limit = 50,
  timeoutMs = 45000,
}) => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const params = new URLSearchParams();
    if (days > 0) params.append("days", String(days));
    if (before) params.append("before", before);
    if (day_window > 0) params.append("day_window", String(day_window));
    params.append("limit", String(Math.min(100, Math.max(1, limit))));

    const query = params.toString();
    const base = getApiAbsoluteBaseUrl();
    const url = `${base}/api/live-chat/conversation/${userId}/${conversationId}?${query}`;
    const response = await liveChatFetch(url, { signal: controller.signal });
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`API ${response.status}: ${errText || response.statusText}`);
    }
    const data = await response.json();

    return {
      ...data,
      success: data?.success ?? false,
      messages: data?.success && Array.isArray(data.messages)
        ? normalizeConversationMessages(data.messages)
        : [],
      has_more: data?.has_more ?? false,
    };
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    console.error("[liveChatApi] fetch messages error:", err);
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
};

/** @param {{ conversationId: string; userId: string; operatorId?: string }} params */
export const endLiveChatConversation = async ({
  conversationId,
  userId,
  operatorId = "operator_001",
}) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const response = await liveChatFetch(`${baseURL}/api/live-chat/end-conversation`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      conversation_id: conversationId,
      user_id: userId,
      operator_id: operatorId,
    }),
  });

  return response.json();
};

/**
 * Mark conversation as read when operator opens it. Persists unread_count=0 in Firestore.
 */
/** @param {{ userId: string; conversationId: string }} params */
export const markConversationRead = async ({ userId, conversationId }) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const response = await liveChatFetch(`${baseURL}/api/live-chat/mark-read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      conversation_id: conversationId,
    }),
  });
  return response.json();
};

/**
 * Edit a bot message's content in live chat (after dislike).
 * Updates the message in Firestore and returns the updated message.
 */
/**
 * @param {{
 *   userId: string;
 *   conversationId: string;
 *   messageId: string;
 *   newContent: string;
 * }} params
 */
export const editLiveChatMessage = async ({
  userId,
  conversationId,
  messageId,
  newContent,
}) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const response = await liveChatFetch(`${baseURL}/api/live-chat/edit-message`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_id: userId,
      conversation_id: conversationId,
      message_id: messageId,
      new_content: newContent,
    }),
  });
  return response.json();
};

/**
 * Get FAQ match context for a message (for FAQ Correction modal).
 */
/** @param {{ userId: string; conversationId: string; messageId: string }} params */
export const fetchFaqMatchContext = async ({ userId, conversationId, messageId }) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const params = new URLSearchParams({ user_id: userId, conversation_id: conversationId, message_id: messageId });
  const response = await liveChatFetch(`${baseURL}/api/live-chat/faq-match-context?${params}`);
  return response.json();
};

/**
 * Update existing FAQ entry's answer (Save Change in FAQ Correction).
 */
/** @param {{ faqId: string; newAnswerText: string; updatedBy?: string; source?: string }} params */
export const faqUpdateAnswer = async ({ faqId, newAnswerText, updatedBy = "operator", source = "live_chat_dislike" }) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const response = await liveChatFetch(`${baseURL}/api/faq/update-answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      faq_id: faqId,
      new_answer_text: newAnswerText,
      updated_by: updatedBy,
      source,
    }),
  });
  return response.json();
};

/**
 * Create new FAQ entry from Live Chat (Save New in FAQ Correction).
 */
/**
 * @param {{
 *   questionText: string;
 *   questionLanguage: string;
 *   answerText: string;
 *   createdBy?: string;
 *   source?: string;
 *   relatedFaqId?: string;
 *   matchSimilarity?: number;
 * }} params
 */
export const faqCreateFromLivechat = async ({
  questionText,
  questionLanguage,
  answerText,
  createdBy = "operator",
  source = "live_chat_dislike",
  relatedFaqId,
  matchSimilarity,
}) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const response = await liveChatFetch(`${baseURL}/api/faq/create-from-livechat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question_text: questionText,
      question_language: questionLanguage,
      answer_text: answerText,
      created_by: createdBy,
      source,
      related_faq_id: relatedFaqId ?? undefined,
      match_similarity: matchSimilarity ?? undefined,
    }),
  });
  return response.json();
};
