/** Shared helpers for MobileLiveChatView (LOC split). */

/** @param {LiveChatMessage | string | null | undefined} lastMessage */
export const previewLastMessage = (lastMessage) => {
  if (!lastMessage) return "";
  if (typeof lastMessage === "string") return lastMessage;
  return String(lastMessage.content || lastMessage.text || "");
};
