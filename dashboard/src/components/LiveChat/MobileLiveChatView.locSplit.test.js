import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { previewLastMessage } from "./MobileLiveChatView.helpers";
import MobileLiveChatView from "./MobileLiveChatView";

const root = path.dirname(fileURLToPath(import.meta.url));

function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("MobileLiveChatView LOC split", () => {
  it("keeps view modules under 500 lines", () => {
    expect(lineCount("MobileLiveChatView.jsx")).toBeLessThan(500);
    expect(lineCount("MobileLiveChatListPane.jsx")).toBeLessThan(500);
    expect(lineCount("MobileLiveChatThreadPane.jsx")).toBeLessThan(500);
    expect(lineCount("MobileLiveChatView.helpers.js")).toBeLessThan(500);
  });

  it("preserves default export and preview helper", () => {
    expect(typeof MobileLiveChatView).toBe("function");
    expect(previewLastMessage(null)).toBe("");
    expect(previewLastMessage("hi")).toBe("hi");
    expect(previewLastMessage({ content: "x" })).toBe("x");
  });
});
