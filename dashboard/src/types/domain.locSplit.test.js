import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));

function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("domain.d.ts LOC split", () => {
  it("keeps domain type modules under 500 lines", () => {
    expect(lineCount("domain.d.ts")).toBeLessThan(500);
    expect(lineCount("domain-core.d.ts")).toBeLessThan(500);
    expect(lineCount("domain-smart.d.ts")).toBeLessThan(500);
    expect(lineCount("domain-content.d.ts")).toBeLessThan(500);
  });

  it("keeps domain.d.ts as reference entrypoint", () => {
    const text = fs.readFileSync(path.join(root, "domain.d.ts"), "utf8");
    expect(text).toContain('domain-core.d.ts');
    expect(text).toContain('domain-smart.d.ts');
    expect(text).toContain('domain-content.d.ts');
  });
});
