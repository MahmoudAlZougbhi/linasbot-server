import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Sidebar from "./Sidebar";
import { makeAuthUser } from "../../testHelpers/renderWithProviders";

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

describe("Sidebar APK download gating", () => {
  it("shows Live Chat APK when liveChat is resolved (including admin)", async () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "admin",
        tenantId: "linas",
        resolvedPermissions: {
          dashboard: true,
          liveChat: true,
          training: false,
          testing: false,
          analytics: true,
          smartMessaging: false,
          settings: false,
          userManagement: false,
          contentManagers: false,
          activityFlow: true,
        },
      }),
    });

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: /Download Live Chat APK/i })).toBeInTheDocument();
  });

  it("hides APK for admin without liveChat in resolvedPermissions", async () => {
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
          settings: true,
          userManagement: true,
          contentManagers: true,
          activityFlow: true,
        },
      }),
    });

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(screen.queryByRole("link", { name: /Download Live Chat APK/i })).not.toBeInTheDocument();
  });

  it("hides APK download for viewers without liveChat permission", async () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "viewer",
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
          activityFlow: true,
        },
      }),
    });

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(screen.queryByRole("link", { name: /Download Live Chat APK/i })).not.toBeInTheDocument();
  });
});
