import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mergeFetchedWithRecentLocal } from "./useLiveChatSSE.helpers";
import { useLiveChatSSE } from "./useLiveChatSSE";

const root = path.dirname(fileURLToPath(import.meta.url));

function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("useLiveChatSSE LOC split", () => {
  it("keeps hook and helpers under 500 lines", () => {
    expect(lineCount("useLiveChatSSE.jsx")).toBeLessThan(500);
    expect(lineCount("useLiveChatSSE.helpers.js")).toBeLessThan(500);
  });

  it("preserves public hook export and merge helper", () => {
    expect(typeof useLiveChatSSE).toBe("function");
    expect(typeof mergeFetchedWithRecentLocal).toBe("function");
    const merged = mergeFetchedWithRecentLocal([], []);
    expect(Array.isArray(merged)).toBe(true);
  });
});
