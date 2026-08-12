import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildUserData, withAuthFetch } from "./AuthContext.helpers";
import { createAuthUserManagement } from "./AuthContext.users";
import { AuthProvider, useAuth } from "./AuthContext";

const root = path.dirname(fileURLToPath(import.meta.url));

function lineCount(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8").split(/\r?\n/).length;
}

describe("AuthContext LOC split", () => {
  it("keeps context modules under 500 lines", () => {
    expect(lineCount("AuthContext.jsx")).toBeLessThan(500);
    expect(lineCount("AuthContext.helpers.js")).toBeLessThan(500);
    expect(lineCount("AuthContext.users.js")).toBeLessThan(500);
  });

  it("preserves public exports and helpers", () => {
    expect(typeof AuthProvider).toBe("function");
    expect(typeof useAuth).toBe("function");
    expect(typeof buildUserData).toBe("function");
    expect(typeof withAuthFetch).toBe("function");
    expect(typeof createAuthUserManagement).toBe("function");
    expect(buildUserData(null)).toBeNull();
    expect(buildUserData({ id: "1", email: "a@test.com", role: "admin" })).toBeNull();
    expect(buildUserData({ id: "1", email: "a@test.com", tenantId: "linas" })).toBeNull();
    expect(buildUserData({ id: "1", email: "a@test.com", role: "admin", tenantId: "linas" })?.tenantId).toBe("linas");
    expect(buildUserData({ id: "1", email: "a@test.com", role: "admin", tenantId: "linas", emailVerified: true })?.emailVerified).toBe(true);
    expect(buildUserData({ id: "1", email: "a@test.com", role: "admin", tenantId: "linas" })?.emailVerified).toBe(false);
  });
});
