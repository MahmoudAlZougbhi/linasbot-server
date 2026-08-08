import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, Navigate } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { PUBLIC_PATHS, PUBLIC_SITE } from "./constants/publicSite";
import Landing from "./pages/public/Landing";
import NotFound from "./pages/NotFound";

vi.mock("./contexts/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
  /** @param {{ children: import('react').ReactNode }} props */
  AuthProvider: ({ children }) => children,
}));

describe("public SaaS landing routes", () => {
  it("renders public home without login redirect", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<div>login-page</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: PUBLIC_SITE.heroTitle })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Create Account" })[0]).toHaveAttribute(
      "href",
      PUBLIC_PATHS.register
    );
    expect(screen.getAllByRole("link", { name: "Log in" })[0]).toHaveAttribute(
      "href",
      PUBLIC_PATHS.login
    );
    expect(screen.queryByText("login-page")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Linas, the friendly AI assistant character/i })).toBeInTheDocument();
  });

  it("keeps privacy/terms/data-deletion footer targets", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Landing />} />
        </Routes>
      </MemoryRouter>
    );

    const privacy = screen.getAllByRole("link", { name: "Privacy Policy" })[0];
    const terms = screen.getAllByRole("link", { name: "Terms of Service" })[0];
    const deletion = screen.getAllByRole("link", { name: "Data Deletion" })[0];
    expect(privacy).toHaveAttribute("href", PUBLIC_PATHS.privacy);
    expect(terms).toHaveAttribute("href", PUBLIC_PATHS.terms);
    expect(deletion).toHaveAttribute("href", PUBLIC_PATHS.dataDeletion);
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", PUBLIC_PATHS.about);
    expect(screen.getAllByRole("link", { name: /Contact/i })[0]).toBeInTheDocument();
  });

  it("redirects /analytics to /app dashboard home", () => {
    render(
      <MemoryRouter initialEntries={["/analytics"]}>
        <Routes>
          <Route path="/app" element={<div>dashboard-app</div>} />
          <Route path="/analytics" element={<Navigate to="/app" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("dashboard-app")).toBeInTheDocument();
  });
});
