import { describe, expect, it } from "vitest";
import { countWords, formatMediaSummary, isLocationsKnowledgeTitle } from "./knowledgeUi";

describe("knowledgeUi", () => {
  it("counts words and media like the Knowledge screenshot", () => {
    expect(countWords("Suitable areas, preparation, and aftercare.")).toBe(5);
    expect(formatMediaSummary([])).toBe("Text only");
    expect(
      formatMediaSummary([
        { kind: "image", mime: "image/jpeg", filename: "a.jpg" },
        { kind: "image", mime: "image/png", filename: "b.png" },
        { kind: "video", mime: "video/mp4", filename: "c.mp4" },
        { kind: "file", mime: "application/pdf", filename: "d.pdf" },
      ]),
    ).toBe("2 images • 1 video • 1 PDF");
    expect(isLocationsKnowledgeTitle("Opening hours & locations")).toBe(true);
  });
});
