import { SYSTEM_ROLES, PERMISSION_KEYS } from "./permissions";

describe("session role defaults", () => {
  it("keeps platform_owner as a system role", () => {
    expect(SYSTEM_ROLES.platform_owner.assignableInTenantUi).toBe(false);
    expect(SYSTEM_ROLES.platform_owner.permissions.userManagement).toBe(true);
  });

  it("keeps liveChat on admin and operator", () => {
    expect(SYSTEM_ROLES.admin.permissions.liveChat).toBe(true);
    expect(SYSTEM_ROLES.operator.permissions.liveChat).toBe(true);
    expect(PERMISSION_KEYS).toContain("liveChat");
  });
});
