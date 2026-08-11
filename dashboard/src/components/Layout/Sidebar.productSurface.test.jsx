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

describe("Sidebar product surface", () => {
  it("restores Live Chat + Interaction Logs for linas and keeps Wave-1 modules hidden", async () => {
    mockUseAuth.mockReturnValue({ user: makeAuthUser({ role: "admin", tenantId: "linas" }) });

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: /AI Setup/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Settings$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Token Wallet/i })).toBeInTheDocument();
    expect(document.querySelector('a[href="/live-chat"]')).toBeTruthy();
    expect(document.querySelector('a[href="/activity-flow"]')).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download Live Chat APK/i })).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: /Testing Lab/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Smart Messaging/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Create Post/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Business AI Platform/i)).toBeInTheDocument();
  });

  it("hides Live Chat ops surface for non-linas SaaS tenants", async () => {
    mockUseAuth.mockReturnValue({ user: makeAuthUser({ role: "admin", tenantId: "acme-gym" }) });

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: /AI Setup/i })).toBeInTheDocument();
    expect(document.querySelector('a[href="/live-chat"]')).toBeNull();
    expect(document.querySelector('a[href="/activity-flow"]')).toBeNull();
    expect(screen.queryByRole("link", { name: /Download Live Chat APK/i })).not.toBeInTheDocument();
  });
});
