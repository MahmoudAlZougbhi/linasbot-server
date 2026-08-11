import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  FILE_ICONS,
  formatDate,
  formatFileSize,
  findTrainingSearchMatches,
} from "./TrainingFileEditor.meta";
import TrainingFileEditor from "./TrainingFileEditor";

const root = path.dirname(fileURLToPath(import.meta.url));

function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("TrainingFileEditor LOC split", () => {
  it("keeps editor modules under 500 lines", () => {
    expect(lineCount("TrainingFileEditor.jsx")).toBeLessThan(500);
    expect(lineCount("TrainingFileEditor.meta.js")).toBeLessThan(500);
    expect(lineCount("TrainingFileEditorSearch.jsx")).toBeLessThan(500);
    expect(lineCount("TrainingFileEditorBackups.jsx")).toBeLessThan(500);
  });

  it("preserves default export and helpers", () => {
    expect(typeof TrainingFileEditor).toBe("function");
    expect(FILE_ICONS.knowledge_base).toBeTruthy();
    expect(formatDate(null)).toBe("Unknown");
    expect(formatFileSize(0)).toBe("0 B");
    expect(findTrainingSearchMatches("Hello world", "world")).toHaveLength(1);
  });
});
