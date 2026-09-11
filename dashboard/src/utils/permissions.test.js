import { describe, expect, it } from "vitest";
import { resolveUserPermissions } from "./permissions";

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

  it("keeps platform_owner userManagement for owner-portal sessions", () => {
    const perms = resolveUserPermissions(testUser({ role: "platform_owner" }));
    expect(perms.userManagement).toBe(true);
  });
});
