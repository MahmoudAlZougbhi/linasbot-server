import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Sidebar from "./Sidebar";
import Training from "../../pages/Training";
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

describe("Sidebar FAQ single entry", () => {
  it("shows AI Setup and no Bot Training / Legacy FAQ nav writers", () => {
    mockUseAuth.mockReturnValue({ user: makeAuthUser({ role: "admin" }) });

    render(
      <MemoryRouter>
        <Sidebar collapsed={false} onToggleCollapse={() => {}} />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: /AI Setup/i })).toHaveAttribute(
      "href",
      "/content-managers"
    );
    expect(screen.queryByRole("link", { name: /FAQ \/ Bot Training/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Legacy FAQ/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^FAQ$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /\/training/i })).not.toBeInTheDocument();
  });
});

describe("Training legacy redirect", () => {
  it("redirects /training to AI Setup FAQ", () => {
    render(
      <MemoryRouter initialEntries={["/training"]}>
        <Routes>
          <Route path="/training" element={<Training />} />
          <Route path="/content-managers/faq" element={<div>CM FAQ canonical</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("CM FAQ canonical")).toBeInTheDocument();
  });
});
