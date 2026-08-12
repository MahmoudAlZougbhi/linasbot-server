import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Sidebar from "./Sidebar";
import { makeAuthUser } from "../../testHelpers/renderWithProviders";
import { SYSTEM_ROLES } from "../../constants/permissions";

const mockUseAuth = vi.fn();
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../../utils/authFetch", () => ({
  authFetch: vi.fn(async () => ({
    ok: true,
    json: async () => ({ ok: true }),
  })),
}));

describe("Sidebar admin permission fail-closed", () => {
  it("denies admin without liveChat / settings in resolvedPermissions", () => {
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
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(document.querySelector('a[href="/live-chat"]')).toBeNull();
    expect(document.querySelector('a[href="/settings"]')).toBeNull();
    expect(document.querySelector('a[href="/content-managers"]')).toBeNull();
    expect(screen.queryByRole("link", { name: /Download Live Chat APK/i })).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/app"]')).toBeTruthy();
  });

  it("shows gated nav when admin has permissions resolved server-side", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "admin",
        tenantId: "linas",
        resolvedPermissions: { ...SYSTEM_ROLES.admin.permissions },
      }),
    });

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(document.querySelector('a[href="/live-chat"]')).toBeTruthy();
    expect(document.querySelector('a[href="/settings"]')).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download Live Chat APK/i })).toBeInTheDocument();
  });
});
