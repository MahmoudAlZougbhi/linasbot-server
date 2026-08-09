import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Settings from "./Settings";

const authFetchMock = vi.fn();
const mockUseAuth = vi.fn();

vi.mock("../utils/authFetch", () => ({
  authFetch: (/** @type {unknown[]} */ ...args) => authFetchMock(...args),
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../components/UserManagement/UserManagement", () => ({
  default: () => <div>user-management-panel</div>,
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
  },
}));

describe("Settings product surface cleanup", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: {
        role: "admin",
        tenantId: "linas",
        resolvedPermissions: { userManagement: true },
      },
      changePassword: vi.fn(),
    });

    authFetchMock.mockImplementation(async (url) => {
      const path = String(url);
      if (path.includes("/api/settings") && !path.includes("/notifications")) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            settings: {
              general: { defaultLanguage: "en" },
              notifications: { notificationsEnabled: true, emailAlerts: true },
            },
          }),
        };
      }
      return { ok: true, json: async () => ({ success: true }) };
    });
  });

  it("keeps Security / Notifications / General and hides Integrations + Wallet + Languages", async () => {
    render(<Settings />);

    expect(await screen.findByRole("button", { name: /General/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Security/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Notifications/i })).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: /Integrations/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Token Wallet/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Languages$/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Human Takeover/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/System language/i).length).toBeGreaterThan(0);
  });
});
