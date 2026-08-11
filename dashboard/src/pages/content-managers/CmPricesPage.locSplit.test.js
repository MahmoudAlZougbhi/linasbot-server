import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { TABS, emptyLabels, labelEn, asRecord } from "./cmPricesHelpers";
import CmPricesPage from "./CmPricesPage";

const root = path.dirname(fileURLToPath(import.meta.url));

function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("CmPricesPage LOC split", () => {
  it("keeps prices modules under 500 lines", () => {
    expect(lineCount("CmPricesPage.jsx")).toBeLessThan(500);
    expect(lineCount("cmPricesHelpers.js")).toBeLessThan(500);
    expect(lineCount("CmPricesSetupPanels.jsx")).toBeLessThan(500);
    expect(lineCount("CmPricesPricingPanels.jsx")).toBeLessThan(500);
  });

  it("preserves default export and helpers", () => {
    expect(typeof CmPricesPage).toBe("function");
    expect(TABS.length).toBeGreaterThan(0);
    expect(emptyLabels()).toEqual({ en: "", ar: "", fr: "", franco: "" });
    expect(labelEn({ en: "X" })).toBe("X");
    expect(asRecord(null)).toEqual({});
  });
});
