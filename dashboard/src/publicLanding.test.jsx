import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, Navigate } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { PUBLIC_PATHS, PUBLIC_SITE } from "./constants/publicSite";
import { PublicLandingLocaleProvider } from "./contexts/PublicLandingLocaleContext";
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

describe("public marketing landing", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        if (String(url).includes("/api/guest-ai/session")) {
          return {
            ok: true,
            status: 200,
            text: async () =>
              JSON.stringify({
                success: true,
                session: {
                  id: "guest-test",
                  questions_used: 0,
                  questions_remaining: 10,
                  max_questions: 10,
                  max_words: 50,
                  messages: [
                    {
                      id: "g1",
                      role: "assistant",
                      content: "Hi — I’m Linas, your reply assistant.",
                      created_at: 1,
                    },
                  ],
                },
              }),
          };
        }
        return { ok: false, status: 404, text: async () => "{}" };
      }),
    );
  });

  const renderLanding = (initial = "/") =>
    render(
      <MemoryRouter initialEntries={[initial]}>
        <PublicLandingLocaleProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<div>login-page</div>} />
            <Route path="/register" element={<Navigate to="/#get-app" replace />} />
          </Routes>
        </PublicLandingLocaleProvider>
      </MemoryRouter>
    );

  it("renders marketing home without login or create-account CTAs", async () => {
    renderLanding("/");

    expect(screen.getByRole("heading", { name: PUBLIC_SITE.heroHeadline })).toBeInTheDocument();
    expect(screen.getAllByText(PUBLIC_SITE.heroTitle).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Create Account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Log in" })).not.toBeInTheDocument();
    expect(screen.queryByText("login-page")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Page language" })).toBeInTheDocument();
    expect(screen.getAllByRole("group", { name: "Download Linas AI" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /Talk to Linas/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Chat with Linas" }));
    await waitFor(() => {
      expect(screen.getByText(/reply assistant/i)).toBeInTheDocument();
    });
  });

  it("switches page language control", async () => {
    renderLanding("/");
    expect(screen.getByRole("group", { name: "Page language" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "ع" }));
    fireEvent.click(screen.getByRole("button", { name: "FR" }));
    expect(screen.getByRole("button", { name: "FR" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps privacy/terms/data-deletion footer targets", () => {
    renderLanding("/");

    const privacy = screen.getAllByRole("link", { name: "Privacy Policy" })[0];
    const terms = screen.getAllByRole("link", { name: "Terms of Service" })[0];
    const deletion = screen.getAllByRole("link", { name: "Data Deletion" })[0];
    expect(privacy).toHaveAttribute("href", PUBLIC_PATHS.privacy);
    expect(terms).toHaveAttribute("href", PUBLIC_PATHS.terms);
    expect(deletion).toHaveAttribute("href", PUBLIC_PATHS.dataDeletion);
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", PUBLIC_PATHS.about);
    expect(screen.getAllByRole("link", { name: /Contact/i })[0]).toBeInTheDocument();
    expect(PUBLIC_SITE.contactEmail).toBe("support@linasai.com");
    expect(screen.getAllByRole("link", { name: PUBLIC_SITE.contactEmail }).length).toBeGreaterThan(0);
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
