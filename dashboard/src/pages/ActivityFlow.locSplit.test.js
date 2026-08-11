import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { formatUsd, costSummary, getEntryKey } from "./ActivityFlow.meta";
import ActivityFlow from "./ActivityFlow";

const root = path.dirname(fileURLToPath(import.meta.url));

function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("ActivityFlow LOC split", () => {
  it("keeps activity flow modules under 500 lines", () => {
    expect(lineCount("ActivityFlow.jsx")).toBeLessThan(500);
    expect(lineCount("ActivityFlow.meta.js")).toBeLessThan(500);
    expect(lineCount("ActivityFlowStep.jsx")).toBeLessThan(500);
    expect(lineCount("ActivityFlowCard.jsx")).toBeLessThan(500);
  });

  it("preserves default export and cost helpers", () => {
    expect(typeof ActivityFlow).toBe("function");
    expect(formatUsd(0)).toBe("$0.0000");
    expect(costSummary({ cost_status: "none" }).label).toBe("No AI cost");
    expect(getEntryKey({ timestamp: "t", user_id: "u" })).toContain("t");
  });
});
