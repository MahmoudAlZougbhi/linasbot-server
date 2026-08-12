import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAuthUserManagement } from "./AuthContext.users";
import { makeAuthUser } from "../testHelpers/renderWithProviders";

describe("createAuthUserManagement userManagement gate", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        json: async () => ({ success: true, users: [], user: { id: "2" } }),
      }))
    );
  });

  it("denies admin without userManagement resolvedPermission", async () => {
    const api = createAuthUserManagement({
      user: makeAuthUser({
        id: "1",
        role: "admin",
        resolvedPermissions: { userManagement: false },
      }),
      setUser: vi.fn(),
    });

    await expect(api.createUser({ email: "a@test.com", password: "x" })).rejects.toThrow(
      /Permission denied/
    );
    await expect(api.updateUser("2", { name: "x" })).rejects.toThrow(/Permission denied/);
    await expect(api.deleteUser("2")).rejects.toThrow(/Permission denied/);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("allows when userManagement is resolved true", async () => {
    const api = createAuthUserManagement({
      user: makeAuthUser({
        id: "1",
        role: "admin",
        resolvedPermissions: { userManagement: true },
      }),
      setUser: vi.fn(),
    });

    await expect(api.createUser({ email: "a@test.com", password: "x" })).resolves.toEqual({
      id: "2",
    });
    expect(fetch).toHaveBeenCalled();
  });

  it("allows platform_owner without relying on admin role bypass", async () => {
    const api = createAuthUserManagement({
      user: makeAuthUser({
        id: "1",
        role: "platform_owner",
        resolvedPermissions: { userManagement: false },
      }),
      setUser: vi.fn(),
    });

    await expect(api.createUser({ email: "a@test.com", password: "x" })).resolves.toEqual({
      id: "2",
    });
  });
});
