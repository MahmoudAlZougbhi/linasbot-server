import { getAxiosErrorCode, isAxiosLikeError } from "../utils/apiValidate";

/**
 * @param {unknown} userId
 * @param {unknown} channel
 * @returns {boolean}
 */
export const isSocialChannelUser = (userId, channel) => {
  const ch = String(channel || "").toLowerCase();
  if (ch === "instagram" || ch === "facebook") return true;
  const id = String(userId || "");
  return /^(?:[a-z0-9][a-z0-9_-]{0,63}:)?(?:instagram|facebook):/i.test(id);
};

export const CHAT_LIST_PAGE_SIZE = 30;
export const MESSAGE_CACHE_TTL_MS = 5 * 60 * 1000;

/** @param {unknown} value @returns {LiveChatConversation[]} */
export const asConversationList = (value) =>
  Array.isArray(value) ? /** @type {LiveChatConversation[]} */ (value) : [];

/** @param {unknown} value @returns {QueueItem[]} */
export const asQueueList = (value) => (Array.isArray(value) ? /** @type {QueueItem[]} */ (value) : []);

/** @param {unknown} value @returns {LiveChatMessage[]} */
export const asMessageList = (value) => (Array.isArray(value) ? /** @type {LiveChatMessage[]} */ (value) : []);

/** @param {unknown} value @returns {string} */
export const asText = (value) => (typeof value === "string" ? value : "");

/** @param {unknown} value @returns {number} */
export const asTimestampMs = (value) => {
  if (!value) return 0;
  const parsed = new Date(/** @type {string | number | Date} */ (value)).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
};

/** @param {LiveChatConversation | null | undefined} conv @returns {conv is LiveChatConversation} */
export const isConversation = (conv) => Boolean(conv);

/** @param {LiveChatMessage} message @returns {string} */
export const messageBody = (message) => asText(message.content) || asText(message.text);

/** @param {unknown} error @returns {boolean} */
export const isGatewayTimeout = (error) => {
  if (getAxiosErrorCode(error) === "ECONNABORTED") return true;
  if (!isAxiosLikeError(error)) return false;
  return error.response?.status === 504;
};

/** @param {LiveChatMessage | string | null | undefined} value @returns {string | undefined} */
export const lastMessageContent = (value) => {
  if (value == null) return undefined;
  if (typeof value === "string") return value;
  return typeof value.content === "string" ? value.content : undefined;
};
