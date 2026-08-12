import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";
import { makeAuthUser } from "../testHelpers/renderWithProviders";
import { SYSTEM_ROLES } from "../constants/permissions";

const mockUseAuth = vi.fn();
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

describe("Dashboard admin permission fail-closed", () => {
  it("hides gated links for admin missing resolvedPermissions", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "admin",
        tenantId: "linas",
        resolvedPermissions: {
          dashboard: true,
          liveChat: false,
          training: false,
          testing: false,
          analytics: true,
          smartMessaging: false,
          settings: false,
          userManagement: false,
          contentManagers: false,
          contentPublish: false,
          activityFlow: false,
        },
      }),
    });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    expect(screen.queryByRole("link", { name: /Live Chat/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Settings$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /AI Setup/i })).not.toBeInTheDocument();
  });

  it("shows links when admin has permissions resolved server-side", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "admin",
        tenantId: "linas",
        resolvedPermissions: { ...SYSTEM_ROLES.admin.permissions },
      }),
    });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: /Live Chat/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Settings$/i })).toBeInTheDocument();
  });
});
