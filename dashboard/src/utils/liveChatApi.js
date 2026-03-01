import { getApiAbsoluteBaseUrl } from "./apiBaseUrl";

export const normalizeConversationMessages = (messages = []) =>
  [...messages].sort((left, right) => {
    const leftTs = new Date(left?.timestamp || 0).getTime();
    const rightTs = new Date(right?.timestamp || 0).getTime();
    return leftTs - rightTs;
  });

export const fetchLiveChatConversationMessages = async ({
  userId,
  conversationId,
  days = 0,
  before = null,
  limit = 50,
  timeoutMs = 45000,
}) => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const params = new URLSearchParams();
    if (days > 0) params.append("days", String(days));
    if (before) params.append("before", before);
    params.append("limit", String(Math.min(100, Math.max(1, limit))));

    const query = params.toString();
    const baseURL = getApiAbsoluteBaseUrl();
    const url = `${baseURL}/api/live-chat/conversation/${userId}/${conversationId}?${query}`;
    const response = await fetch(url, { signal: controller.signal });
    const data = await response.json();

    return {
      ...data,
      messages: data?.success && Array.isArray(data.messages)
        ? normalizeConversationMessages(data.messages)
        : [],
      has_more: data?.has_more ?? false,
    };
  } finally {
    clearTimeout(timeoutId);
  }
};

export const endLiveChatConversation = async ({
  conversationId,
  userId,
  operatorId = "operator_001",
}) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const response = await fetch(`${baseURL}/api/live-chat/end-conversation`, {
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
 * Edit a bot message's content in live chat (after dislike).
 * Updates the message in Firestore and returns the updated message.
 */
export const editLiveChatMessage = async ({
  userId,
  conversationId,
  messageId,
  newContent,
}) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const response = await fetch(`${baseURL}/api/live-chat/edit-message`, {
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
export const fetchFaqMatchContext = async ({ userId, conversationId, messageId }) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const params = new URLSearchParams({ user_id: userId, conversation_id: conversationId, message_id: messageId });
  const response = await fetch(`${baseURL}/api/live-chat/faq-match-context?${params}`);
  return response.json();
};

/**
 * Update existing FAQ entry's answer (Save Change in FAQ Correction).
 */
export const faqUpdateAnswer = async ({ faqId, newAnswerText, updatedBy = "operator", source = "live_chat_dislike" }) => {
  const baseURL = getApiAbsoluteBaseUrl();
  const response = await fetch(`${baseURL}/api/faq/update-answer`, {
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
  const response = await fetch(`${baseURL}/api/faq/create-from-livechat`, {
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
