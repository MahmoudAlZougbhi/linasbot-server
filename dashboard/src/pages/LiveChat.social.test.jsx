import { describe, expect, it } from "vitest";
import { isSocialChannelUser } from "./LiveChat";

describe("LiveChat social read-only detection", () => {
  it("detects instagram and facebook channels", () => {
    expect(isSocialChannelUser("instagram:123", null)).toBe(true);
    expect(isSocialChannelUser("facebook:456", null)).toBe(true);
    expect(isSocialChannelUser("9613000000", "instagram")).toBe(true);
    expect(isSocialChannelUser("9613000000", "facebook")).toBe(true);
  });

  it("does not flag WhatsApp phone users", () => {
    expect(isSocialChannelUser("9613000000", "whatsapp")).toBe(false);
    expect(isSocialChannelUser("9613000000", null)).toBe(false);
    expect(isSocialChannelUser("+9613000000", "")).toBe(false);
  });
});
