import { describe, expect, it } from "vitest";
import {
  canAccessPath,
  getDefaultPath,
  hasPermission,
  resolveUserPermissions,
} from "./permissions";

/** @param {Partial<DashboardUser> & { role: string }} user */
const testUser = (user) => /** @type {DashboardUser} */ ({
  id: "test-user",
  email: "test@example.com",
  ...user,
});

describe("permissions utils", () => {
  it("resolves operator role defaults", () => {
    const perms = resolveUserPermissions(testUser({ role: "operator" }));
    expect(perms.liveChat).toBe(true);
    expect(perms.settings).toBe(false);
  });

  it("respects custom permission overrides on the user", () => {
    const perms = resolveUserPermissions(testUser({
      role: "viewer",
      permissions: { liveChat: true, settings: true },
    }));
    expect(perms.liveChat).toBe(true);
    expect(perms.settings).toBe(true);
    expect(perms.training).toBe(false);
  });

  it("blocks viewer from live chat path", () => {
    const viewer = testUser({ role: "viewer" });
    expect(hasPermission(viewer, "liveChat")).toBe(false);
    expect(canAccessPath(viewer, "/live-chat")).toBe(false);
    expect(getDefaultPath(viewer)).toBe("/app");
  });

  it("allows admin to access content managers and activity flow", () => {
    const admin = testUser({ role: "admin" });
    expect(canAccessPath(admin, "/content-managers")).toBe(true);
    expect(canAccessPath(admin, "/activity-flow")).toBe(true);
  });
});
