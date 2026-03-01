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
  timeoutMs = 90000,
}) => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const params = new URLSearchParams();
    if (days > 0) params.append("days", String(days));
    if (before) params.append("before", before);

    const query = params.toString();
    const baseURL = getApiAbsoluteBaseUrl();
    const url = `${baseURL}/api/live-chat/conversation/${userId}/${conversationId}${query ? `?${query}` : ""}`;
    const response = await fetch(url, { signal: controller.signal });
    const data = await response.json();

    return {
      ...data,
      messages: data?.success && Array.isArray(data.messages)
        ? normalizeConversationMessages(data.messages)
        : [],
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
