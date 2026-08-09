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

describe("Sidebar Wave 1 product surface", () => {
  it("hides disabled modules for admin including linas", async () => {
    mockUseAuth.mockReturnValue({ user: makeAuthUser({ role: "admin", tenantId: "linas" }) });

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: /Content Managers/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Settings$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Token Wallet/i })).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: /Testing Lab/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Smart Messaging/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Live Chat$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Interaction Logs/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Create Post/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Download Live Chat APK/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Business AI Platform/i)).toBeInTheDocument();
  });
});
