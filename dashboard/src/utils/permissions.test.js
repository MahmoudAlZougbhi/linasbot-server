import { describe, expect, it } from "vitest";
import {
  canAccessPath,
  getDefaultPath,
  hasPermission,
  resolveUserPermissions,
} from "./permissions";

describe("permissions utils", () => {
  it("resolves operator role defaults", () => {
    const perms = resolveUserPermissions({ role: "operator" });
    expect(perms.liveChat).toBe(true);
    expect(perms.settings).toBe(false);
  });

  it("respects custom permission overrides on the user", () => {
    const perms = resolveUserPermissions({
      role: "viewer",
      permissions: { liveChat: true, settings: true },
    });
    expect(perms.liveChat).toBe(true);
    expect(perms.settings).toBe(true);
    expect(perms.training).toBe(false);
  });

  it("blocks viewer from live chat path", () => {
    const viewer = { role: "viewer" };
    expect(hasPermission(viewer, "liveChat")).toBe(false);
    expect(canAccessPath(viewer, "/live-chat")).toBe(false);
    expect(getDefaultPath(viewer)).toBe("/");
  });

  it("allows admin to access content managers and activity flow", () => {
    const admin = { role: "admin" };
    expect(canAccessPath(admin, "/content-managers")).toBe(true);
    expect(canAccessPath(admin, "/activity-flow")).toBe(true);
  });
});
