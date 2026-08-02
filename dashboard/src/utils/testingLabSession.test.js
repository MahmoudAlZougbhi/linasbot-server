import { describe, expect, it } from "vitest";
import {
  appendMessagesToLabSessions,
  appendTurnToLabSessions,
  buildLabSessionKey,
  clearLabSession,
  emptyLabSession,
  normalizeLabChannel,
  parseStoredLabSessions,
  splitBotOutputIntoMessages,
  toChatMessages,
} from "./testingLabSession";

describe("testingLabSession helpers", () => {
  it("builds a canonical session key that includes the social channel", () => {
    expect(buildLabSessionKey("montymobile", "instagram", "123")).toBe(
      "montymobile:instagram:123"
    );
    expect(buildLabSessionKey("montymobile", "facebook", "123")).toBe(
      "montymobile:facebook:123"
    );
    expect(buildLabSessionKey("montymobile", "", "123")).toBe("montymobile:wa:123");
    expect(normalizeLabChannel("Instagram")).toBe("instagram");
  });

  it("keeps Chat View and Result Cards on the same session store", () => {
    const key = buildLabSessionKey("montymobile", "instagram", "555");
    /** @type {Record<string, { messages: TestingChatMessage[], turns: TestingTestResult[] }>} */
    let sessions = {};
    sessions = appendMessagesToLabSessions(
      sessions,
      key,
      toChatMessages([{ role: "user", content: "Hello" }])
    );
    sessions = appendMessagesToLabSessions(
      sessions,
      key,
      toChatMessages([{ role: "assistant", content: "Hi there" }])
    );
    sessions = appendTurnToLabSessions(sessions, key, {
      id: 1,
      type: "text",
      input: "Hello",
      output: "Hi there",
      success: true,
      channel: "instagram",
    });

    const active = sessions[key];
    expect(active).toBeTruthy();
    expect(active?.messages.map((/** @type {TestingChatMessage} */ m) => m.content)).toEqual([
      "Hello",
      "Hi there",
    ]);
    expect(active?.turns).toHaveLength(1);
    expect(active?.turns[0]?.output).toBe("Hi there");

    const cleared = clearLabSession(sessions, key);
    expect(cleared[key]).toBeUndefined();
    expect(emptyLabSession()).toEqual({ messages: [], turns: [] });
  });

  it("ignores legacy v1-shaped storage without messages/turns objects", () => {
    expect(parseStoredLabSessions({ "montymobile:123": [{ id: "x" }] })).toEqual(
      {}
    );
    const parsed = parseStoredLabSessions({
      "montymobile:instagram:123": {
        messages: [{ id: "1", role: "user", type: "text", content: "A", timestamp: "1" }],
        turns: [],
      },
    });
    expect(parsed["montymobile:instagram:123"]?.messages).toHaveLength(1);
  });

  it("does not invent bot chunks for empty output", () => {
    expect(splitBotOutputIntoMessages("")).toEqual([]);
    expect(splitBotOutputIntoMessages("line1\n\nline2")).toEqual(["line1", "line2"]);
  });
});
