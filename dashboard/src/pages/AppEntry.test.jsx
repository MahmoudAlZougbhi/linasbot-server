import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { makeAuthUser } from "../testHelpers/renderWithProviders";
import AppEntry, { UseMobileAppPage } from "./AppEntry";

const mockUseAuth = vi.fn();
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

describe("AppEntry", () => {
  it("sends platform_owner to /owner", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({ role: "platform_owner", email: "owner@linas.ai" }),
      loading: false,
    });
    render(
      <MemoryRouter initialEntries={["/app"]}>
        <Routes>
          <Route path="/app" element={<AppEntry />} />
          <Route path="/owner" element={<div>owner-portal</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("owner-portal")).toBeInTheDocument();
  });

  it("shows the mobile-app stub for tenant admin after login", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({ role: "admin", email: "admin@linas.ai" }),
      loading: false,
      logout: vi.fn(),
    });
    render(
      <MemoryRouter>
        <AppEntry />
      </MemoryRouter>
    );
    expect(screen.getByRole("heading", { name: "Use the Linas AI mobile app" })).toBeInTheDocument();
    expect(screen.getByText("Signed in as admin@linas.ai")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("does not show signed-in controls for anonymous /app", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false, logout: vi.fn() });
    render(
      <MemoryRouter>
        <UseMobileAppPage />
      </MemoryRouter>
    );
    expect(screen.getByRole("heading", { name: "Use the Linas AI mobile app" })).toBeInTheDocument();
    expect(screen.queryByText(/Signed in as/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });
});
