import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PermissionsProvider, usePermissions } from "./PermissionsContext";
import { makeAuthUser } from "../testHelpers/renderWithProviders";

const mockUseAuth = vi.fn();
vi.mock("./AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

function Probe() {
  const { hasPermission, canManageUsers, isAdmin } = usePermissions();
  return (
    <div>
      <span data-testid="liveChat">{String(hasPermission("liveChat"))}</span>
      <span data-testid="canManage">{String(canManageUsers())}</span>
      <span data-testid="isAdmin">{String(isAdmin())}</span>
    </div>
  );
}

describe("PermissionsContext fail-closed", () => {
  it("denies admin without resolvedPermissions (no role bypass)", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "admin",
        resolvedPermissions: {
          dashboard: true,
          liveChat: false,
          userManagement: false,
        },
      }),
    });

    render(
      <PermissionsProvider>
        <Probe />
      </PermissionsProvider>
    );

    expect(screen.getByTestId("liveChat")).toHaveTextContent("false");
    expect(screen.getByTestId("canManage")).toHaveTextContent("false");
    expect(screen.getByTestId("isAdmin")).toHaveTextContent("true");
  });

  it("allows platform_owner for canManageUsers", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "platform_owner",
        resolvedPermissions: { userManagement: false, liveChat: false },
      }),
    });

    render(
      <PermissionsProvider>
        <Probe />
      </PermissionsProvider>
    );

    expect(screen.getByTestId("canManage")).toHaveTextContent("true");
    expect(screen.getByTestId("liveChat")).toHaveTextContent("false");
  });
});
