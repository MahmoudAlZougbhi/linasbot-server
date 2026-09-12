import { describe, expect, it } from "vitest";
import { buildUserData, postLoginPath } from "./AuthContext.helpers";

const tenantUser = {
  id: "1",
  email: "a@test.com",
  tenantId: "linas",
  status: "active",
};

describe("postLoginPath", () => {
  it("sends platform owners to /owner after login", () => {
    expect(postLoginPath({ role: "platform_owner" })).toBe("/owner");
    expect(postLoginPath({ role: "PLATFORM_OWNER" }, "/app")).toBe("/owner");
    expect(postLoginPath({ role: "platform_owner" }, "/owner/users")).toBe("/owner/users");
  });

  it("keeps tenant operators on /app and blocks /owner", () => {
    expect(postLoginPath({ role: "admin" })).toBe("/app");
    expect(postLoginPath({ role: "admin" }, "/app")).toBe("/app");
    expect(postLoginPath({ role: "admin" }, "/owner")).toBe("/app");
    expect(postLoginPath({ role: "admin" }, "/owner/users")).toBe("/app");
    expect(postLoginPath({ role: "operator" }, "/#get-app")).toBe("/#get-app");
  });
});

describe("buildUserData role", () => {
  it("normalizes mixed-case platform_owner so AppEntry can match", () => {
    const user = buildUserData({ ...tenantUser, role: "Platform_Owner" });
    expect(user?.role).toBe("platform_owner");
  });
});
