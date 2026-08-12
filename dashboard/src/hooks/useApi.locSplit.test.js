import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { useApi } from "./useApi";

const root = path.dirname(fileURLToPath(import.meta.url));

/** @param {string} rel */
function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("useApi LOC split", () => {
  it("keeps api hook modules under 500 lines", () => {
    expect(lineCount("useApi.jsx")).toBeLessThan(500);
    expect(lineCount("useApiClient.js")).toBeLessThan(500);
    expect(lineCount("useApiTesting.js")).toBeLessThan(500);
    expect(lineCount("useApiQA.js")).toBeLessThan(500);
    expect(lineCount("useApiTraining.js")).toBeLessThan(500);
    expect(lineCount("useApiContent.js")).toBeLessThan(500);
  });

  it("preserves named useApi export", () => {
    expect(typeof useApi).toBe("function");
  });
});
