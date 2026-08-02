import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Settings from "./Settings";
import { expectAccessibleControls } from "../testHelpers/a11ySmoke";

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

describe("Settings integrations", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { role: "admin", resolvedPermissions: { userManagement: true } },
      changePassword: vi.fn(),
    });

    authFetchMock.mockImplementation(async (url) => {
      const path = String(url);
      if (path.includes("/api/settings/integrations")) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            integrations: [
              {
                name: "OpenAI",
                service: "LLM",
                configured: true,
                notes: "API key present",
                secret: "sk-should-never-render",
                api_key: "also-hidden",
              },
            ],
          }),
        };
      }
      if (path.includes("/api/settings")) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            settings: {
              general: {},
              notifications: {},
              clinic: { branchHolidays: [] },
            },
          }),
        };
      }
      return { ok: true, json: async () => ({ success: true }) };
    });
  });

  it("shows integration status without exposing secrets", async () => {
    render(<Settings />);

    fireEvent.click(await screen.findByRole("button", { name: "Integrations" }));

    await waitFor(() => {
      expect(screen.getByText(/Integration status \(secrets are never displayed\)/i)).toBeInTheDocument();
    });

    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Configured")).toBeInTheDocument();
    expect(screen.getByText(/Secrets are never displayed in the dashboard/i)).toBeInTheDocument();
    expect(screen.queryByText(/sk-should-never-render/)).not.toBeInTheDocument();
    expect(screen.queryByText(/also-hidden/)).not.toBeInTheDocument();

    expectAccessibleControls([{ role: "button", name: "Health check" }]);
  });

  it("shows integrations error state from API failure", async () => {
    authFetchMock.mockImplementation(async (url) => {
      if (String(url).includes("/api/settings/integrations")) {
        return {
          ok: false,
          status: 403,
          json: async () => ({ success: false, error: "Forbidden" }),
        };
      }
      return {
        ok: true,
        json: async () => ({ success: true, settings: { general: {}, notifications: {}, clinic: {} } }),
      };
    });

    render(<Settings />);
    fireEvent.click(await screen.findByRole("button", { name: "Integrations" }));

    expect(await screen.findByText("Forbidden")).toBeInTheDocument();
  });
});
