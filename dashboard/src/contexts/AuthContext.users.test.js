import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAuthUserManagement } from "./AuthContext.users";
import { makeAuthUser } from "../testHelpers/renderWithProviders";

describe("createAuthUserManagement refreshUser", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        json: async () => ({
          success: true,
          user: {
            id: "1",
            email: "a@test.com",
            role: "platform_owner",
            tenantId: "linas",
            status: "active",
          },
        }),
      }))
    );
  });

  it("refreshes the signed-in user from /api/auth/session", async () => {
    const setUser = vi.fn();
    const api = createAuthUserManagement({
      user: makeAuthUser({
        id: "1",
        role: "platform_owner",
        tenantId: "linas",
      }),
      setUser,
    });

    await api.refreshUser();
    expect(fetch).toHaveBeenCalled();
    expect(setUser).toHaveBeenCalled();
  });

  it("does nothing when there is no signed-in user", async () => {
    const setUser = vi.fn();
    const api = createAuthUserManagement({ user: null, setUser });
    await api.refreshUser();
    expect(fetch).not.toHaveBeenCalled();
    expect(setUser).not.toHaveBeenCalled();
  });
});
