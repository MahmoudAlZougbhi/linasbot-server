import { render, screen } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ProtectedRoute from "./components/Auth/ProtectedRoute";
import { makeAuthUser } from "./testHelpers/renderWithProviders";
import { getDefaultPath } from "./utils/permissions";

const mockUseAuth = vi.fn();
vi.mock("./contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

/**
 * Mirrors landing-only App.jsx route policy used after operator SPA removal:
 * marketing + thin auth; obsolete operator paths → /#get-app.
 */
function LandingOnlyRoutes() {
  return (
    <Routes>
      <Route path="/" element={<div>public-landing</div>} />
      <Route path="/login" element={<div>login-page</div>} />
      <Route path="/forgot-password" element={<div>forgot-page</div>} />
      <Route path="/reset-password" element={<div>reset-page</div>} />
      <Route path="/verify-email" element={<div>verify-page</div>} />
      <Route path="/register" element={<Navigate to="/#get-app" replace />} />
      <Route path="/mobile/live-chat" element={<Navigate to="/#get-app" replace />} />
      <Route path="/live-chat" element={<Navigate to="/#get-app" replace />} />
      <Route path="/content-managers/*" element={<Navigate to="/#get-app" replace />} />
      <Route path="/activity-flow" element={<Navigate to="/#get-app" replace />} />
      <Route path="/settings" element={<Navigate to="/#get-app" replace />} />
      <Route path="/app" element={<div>use-mobile-app</div>} />
      <Route
        path="/protected-demo"
        element={
          <ProtectedRoute>
            <div>protected-ok</div>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

describe("landing-only auth and obsolete routes", () => {
  it("auth default path is / for entitled roles", () => {
    expect(getDefaultPath(makeAuthUser({ role: "admin" }))).toBe("/");
    expect(getDefaultPath(makeAuthUser({ role: "operator" }))).toBe("/");
  });

  it("unauth default via ProtectedRoute goes to /login", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    render(
      <MemoryRouter initialEntries={["/protected-demo"]}>
        <LandingOnlyRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("serves reset-password and verify-email thin auth pages", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    const { unmount } = render(
      <MemoryRouter initialEntries={["/reset-password"]}>
        <LandingOnlyRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("reset-page")).toBeInTheDocument();
    unmount();
    render(
      <MemoryRouter initialEntries={["/verify-email"]}>
        <LandingOnlyRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("verify-page")).toBeInTheDocument();
  });

  it("redirects obsolete operator paths including /mobile/live-chat to get-app hash", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    for (const path of [
      "/mobile/live-chat",
      "/live-chat",
      "/activity-flow",
      "/settings",
      "/register",
      "/content-managers/faq",
    ]) {
      const { unmount } = render(
        <MemoryRouter initialEntries={[path]}>
          <LandingOnlyRoutes />
        </MemoryRouter>
      );
      // Navigate to="/#get-app" resolves to public landing (/) in MemoryRouter
      expect(screen.getByText("public-landing")).toBeInTheDocument();
      expect(screen.queryByText("protected-ok")).not.toBeInTheDocument();
      unmount();
    }
  });

  it("keeps /app as use-mobile stub rather than operator dashboard", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({ role: "admin" }),
      loading: false,
    });
    render(
      <MemoryRouter initialEntries={["/app"]}>
        <LandingOnlyRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("use-mobile-app")).toBeInTheDocument();
  });

  it("allows authenticated user through ProtectedRoute when no requiredPermission", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({ role: "operator" }),
      loading: false,
    });
    render(
      <MemoryRouter initialEntries={["/protected-demo"]}>
        <LandingOnlyRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("protected-ok")).toBeInTheDocument();
  });

  it("serves forgot-password thin auth page for recovery links", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    render(
      <MemoryRouter initialEntries={["/forgot-password"]}>
        <LandingOnlyRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("forgot-page")).toBeInTheDocument();
  });
});
