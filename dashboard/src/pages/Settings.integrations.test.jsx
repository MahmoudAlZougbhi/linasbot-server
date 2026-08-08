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

  it("offers server-side Meta onboarding without token-entry fields", async () => {
    authFetchMock.mockImplementation(async (url) => {
      const path = String(url);
      if (path === "/api/meta/connections") {
        return {
          ok: true,
          json: async () => ({
            success: true,
            registry_enabled: true,
            apps: [
              {
                key: "linas_first_party",
                app_id: "2963733803971681",
                classification: "own_business",
                enabled: true,
                oauth_configured: true,
                advanced_access_approved: true,
              },
            ],
            connections: [
              {
                binding_id: "binding-one",
                tenant_id: "linas",
                channel: "facebook",
                asset_id: "378696005334409",
                asset_id_masked: "378…409",
                app_key: "linas_first_party",
                app_label: "Lina Meta app",
                status: "active",
                generation: 1,
                token_status: "valid",
                page_name: "Lina's Laser Clinics",
              },
            ],
            authorizations: [
              {
                authorized_meta_user_id_hash: "auth-hash",
                app_key: "linas_first_party",
                app_label: "Lina Meta app",
                authorization_title: "Meta authorization — App A",
                assets: [
                  {
                    binding_id: "binding-one",
                    tenant_id: "linas",
                    channel: "facebook",
                    asset_id: "378696005334409",
                    asset_id_masked: "378…409",
                    app_key: "linas_first_party",
                    app_label: "Lina Meta app",
                    status: "active",
                    generation: 1,
                    token_status: "valid",
                    page_name: "Lina's Laser Clinics",
                  },
                ],
              },
            ],
          }),
        };
      }
      if (path.includes("/api/settings/integrations")) {
        return { ok: true, json: async () => ({ success: true, integrations: [] }) };
      }
      if (path.includes("/api/settings")) {
        return {
          ok: true,
          json: async () => ({ success: true, settings: { general: {}, notifications: {}, clinic: {} } }),
        };
      }
      return { ok: true, json: async () => ({ success: true }) };
    });

    render(<Settings />);
    fireEvent.click(await screen.findByRole("button", { name: "Integrations" }));

    expect(await screen.findByRole("button", { name: "Add / Manage Facebook & Instagram" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Connect Instagram" })).not.toBeInTheDocument();
    expect(screen.getByText("Meta authorization — App A")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.queryByLabelText(/access token/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/app secret/i)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/998877665544/)).not.toBeInTheDocument();
  });

  it("starts unified Meta OAuth when the primary button is clicked", async () => {
    authFetchMock.mockImplementation(async (url, options) => {
      const path = String(url);
      if (path === "/api/meta/connections/start") {
        expect(options?.body).toBe(JSON.stringify({ channel: "unified" }));
        return {
          ok: true,
          json: async () => ({
            success: true,
            authorization_url: "https://www.facebook.com/v24.0/dialog/oauth?state=opaque",
          }),
        };
      }
      if (path === "/api/meta/connections") {
        return {
          ok: true,
          json: async () => ({
            success: true,
            registry_enabled: true,
            apps: [
              {
                key: "linas_first_party",
                app_id: "2963733803971681",
                classification: "own_business",
                enabled: true,
                oauth_configured: true,
                advanced_access_approved: true,
              },
            ],
            connections: [],
            authorizations: [],
          }),
        };
      }
      if (path.includes("/api/settings/integrations")) {
        return { ok: true, json: async () => ({ success: true, integrations: [] }) };
      }
      if (path.includes("/api/settings")) {
        return {
          ok: true,
          json: async () => ({ success: true, settings: { general: {}, notifications: {}, clinic: {} } }),
        };
      }
      return { ok: true, json: async () => ({ success: true }) };
    });

    render(<Settings />);
    fireEvent.click(await screen.findByRole("button", { name: "Integrations" }));
    fireEvent.click(await screen.findByRole("button", { name: "Add / Manage Facebook & Instagram" }));

    await waitFor(() => {
      expect(authFetchMock).toHaveBeenCalledWith(
        "/api/meta/connections/start",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ channel: "unified" }),
        }),
      );
    });
  });

  it("explains disabled Connect button when App A Login config is missing", async () => {
    authFetchMock.mockImplementation(async (url) => {
      const path = String(url);
      if (path === "/api/meta/connections") {
        return {
          ok: true,
          json: async () => ({
            success: true,
            registry_enabled: true,
            apps: [
              {
                key: "linas_first_party",
                app_id: "2963733803971681",
                classification: "own_business",
                enabled: true,
                oauth_configured: false,
                advanced_access_approved: true,
              },
            ],
            connections: [],
          }),
        };
      }
      if (path.includes("/api/settings/integrations")) {
        return { ok: true, json: async () => ({ success: true, integrations: [] }) };
      }
      if (path.includes("/api/settings")) {
        return {
          ok: true,
          json: async () => ({ success: true, settings: { general: {}, notifications: {}, clinic: {} } }),
        };
      }
      return { ok: true, json: async () => ({ success: true }) };
    });

    render(<Settings />);
    fireEvent.click(await screen.findByRole("button", { name: "Integrations" }));

    expect(await screen.findByRole("button", { name: "Add / Manage Facebook & Instagram" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Connect Instagram" })).not.toBeInTheDocument();
    expect(screen.getByText(/META_APP_A_LOGIN_CONFIG_ID/i)).toBeInTheDocument();
  });

  it("shows Reconnect for disconnected Lina first-party bindings with a valid token", async () => {
    authFetchMock.mockImplementation(async (url) => {
      const path = String(url);
      if (path === "/api/meta/connections") {
        return {
          ok: true,
          json: async () => ({
            success: true,
            registry_enabled: true,
            apps: [
              {
                key: "saas_tech_provider",
                app_id: "",
                classification: "tech_provider",
                enabled: false,
                oauth_configured: false,
                advanced_access_approved: false,
              },
            ],
            connections: [
              {
                binding_id: "fb-lina",
                tenant_id: "linas",
                channel: "facebook",
                app_key: "linas_first_party",
                app_label: "Lina Meta app",
                status: "disconnected",
                token_status: "valid",
              },
            ],
            authorizations: [
              {
                authorized_meta_user_id_hash: "auth-hash",
                app_key: "linas_first_party",
                app_label: "Lina Meta app",
                authorization_title: "Meta authorization — App A",
                assets: [
                  {
                    binding_id: "fb-lina",
                    tenant_id: "linas",
                    channel: "facebook",
                    app_key: "linas_first_party",
                    app_label: "Lina Meta app",
                    status: "disconnected",
                    token_status: "valid",
                  },
                ],
              },
            ],
          }),
        };
      }
      if (path.includes("/api/settings/integrations")) {
        return { ok: true, json: async () => ({ success: true, integrations: [] }) };
      }
      if (path.includes("/api/settings")) {
        return {
          ok: true,
          json: async () => ({ success: true, settings: { general: {}, notifications: {}, clinic: {} } }),
        };
      }
      return { ok: true, json: async () => ({ success: true }) };
    });

    render(<Settings />);
    fireEvent.click(await screen.findByRole("button", { name: "Integrations" }));

    expect(await screen.findByRole("button", { name: "Reconnect" })).toBeEnabled();
    expect(screen.getByText("disconnected")).toBeInTheDocument();
  });
});
