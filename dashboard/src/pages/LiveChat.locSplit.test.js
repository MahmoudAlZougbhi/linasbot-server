import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import LiveChat, { isSocialChannelUser } from "./LiveChat";

const root = path.dirname(fileURLToPath(import.meta.url));

function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("LiveChat LOC split", () => {
  it("keeps live chat modules under 500 lines", () => {
    const files = [
      "LiveChat.jsx",
      "LiveChat.helpers.js",
      "useLiveChatShared.js",
      "useLiveChatList.js",
      "useLiveChatFilters.js",
      "useLiveChatEffects.js",
      "useLiveChatSession.js",
      "useLiveChatSelection.js",
      "useLiveChatData.js",
      "useLiveChatPaging.js",
      "useLiveChatActions.js",
      "useLiveChatFeedback.js",
      "useLiveChatController.js",
      "LiveChatModals.jsx",
      "LiveChatSidebar.jsx",
      "LiveChatBotOverlay.jsx",
      "LiveChatThreadHeader.jsx",
      "LiveChatThreadMessages.jsx",
      "LiveChatThread.jsx",
      "LiveChatDetails.jsx",
    ];
    for (const rel of files) {
      expect(lineCount(rel), rel).toBeLessThan(500);
    }
  });

  it("preserves default export and social-channel helper", () => {
    expect(typeof LiveChat).toBe("function");
    expect(isSocialChannelUser("instagram:abc", "instagram")).toBe(true);
    expect(isSocialChannelUser("9613000000", "whatsapp")).toBe(false);
  });
});
