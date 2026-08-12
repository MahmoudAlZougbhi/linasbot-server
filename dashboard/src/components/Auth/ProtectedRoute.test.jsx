import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ProtectedRoute from "./ProtectedRoute";
import { makeAuthUser } from "../../testHelpers/renderWithProviders";

const mockUseAuth = vi.fn();
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

describe("ProtectedRoute", () => {
  it("shows loading screen while auth is resolving", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: true });
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <Routes>
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <div>secret</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("redirects unauthenticated users to login", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <Routes>
          <Route path="/login" element={<div>login-page</div>} />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <div>secret</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("redirects viewer away from settings to default allowed path", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({ role: "viewer", resolvedPermissions: { dashboard: true } }),
      loading: false,
    });
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <Routes>
          <Route path="/settings" element={<ProtectedRoute><div>settings</div></ProtectedRoute>} />
          <Route path="/" element={<div>landing-home</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("landing-home")).toBeInTheDocument();
  });

  it("blocks requiredPermission when user lacks feature", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "operator",
        resolvedPermissions: { dashboard: true, liveChat: false },
      }),
      loading: false,
    });
    render(
      <MemoryRouter initialEntries={["/live-chat"]}>
        <Routes>
          <Route
            path="/live-chat"
            element={
              <ProtectedRoute requiredPermission="liveChat">
                <div>live-chat-page</div>
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<div>landing-home</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("landing-home")).toBeInTheDocument();
  });

  it("denies admin without requiredPermission (fail-closed, no admin bypass)", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({
        role: "admin",
        resolvedPermissions: { dashboard: true, liveChat: false, settings: true },
      }),
      loading: false,
    });
    render(
      <MemoryRouter initialEntries={["/live-chat"]}>
        <Routes>
          <Route
            path="/live-chat"
            element={
              <ProtectedRoute requiredPermission="liveChat">
                <div>live-chat-page</div>
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<div>landing-home</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.queryByText("live-chat-page")).not.toBeInTheDocument();
    expect(screen.getByText("landing-home")).toBeInTheDocument();
  });
});
