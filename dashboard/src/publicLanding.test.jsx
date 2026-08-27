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
    /** @param {string} query */
    window.matchMedia = (query) => ({
      matches: String(query).includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    });
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        const href = String(url);
        if (href.includes("/api/guest-ai/session")) {
          return {
            ok: true,
            status: 200,
            text: async () =>
              JSON.stringify({
                success: true,
                session: {
                  id: "guest-test",
                  limit_reached: false,
                  max_input_tokens: 500,
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
            json: async () => ({
              success: true,
              session: {
                id: "guest-test",
                limit_reached: false,
                max_input_tokens: 500,
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
        if (href.includes("/api/public/landing-stats")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              success: true,
              businesses_using_linas: 4,
              messages_replied: 10,
              comments_replied: 2,
              ai_replies: 12,
              requests: 1,
            }),
          };
        }
        if (href.includes("/api/public/plans")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              success: true,
              plans: [
                {
                  plan_id: "lite",
                  display_name: "Lite",
                  price_usd: 9.99,
                  included_credits: 7000,
                },
              ],
            }),
          };
        }
        return { ok: false, status: 404, text: async () => "{}", json: async () => ({}) };
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

  it("renders approved marketing home without login or create-account CTAs", async () => {
    renderLanding("/");

    expect(screen.getByRole("heading", { name: PUBLIC_SITE.heroHeadline })).toBeInTheDocument();
    expect(screen.getByText(PUBLIC_SITE.heroKicker)).toBeInTheDocument();
    expect(screen.getByText(PUBLIC_SITE.heroConnect)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download app" })).toBeInTheDocument();
    expect(screen.getByText("Knowledge updated")).toBeInTheDocument();
    expect(screen.getByText("Off day saved")).toBeInTheDocument();
    expect(screen.getByText("5 channels connected")).toBeInTheDocument();
    expect(screen.getByText("What would you like to teach me about your business?")).toBeInTheDocument();
    expect(screen.getByText("Every new client gets a free skin consultation.")).toBeInTheDocument();
    expect(screen.getByText(/hydrating serum/i)).toBeInTheDocument();
    expect(screen.getByText(/Saved to Products/i)).toBeInTheDocument();
    expect(screen.getByText(/book an appointment/i)).toBeInTheDocument();
    expect(screen.getByText(/Appointment requests go to your team/i)).toBeInTheDocument();
    expect(screen.getByText("Work with Linas")).toBeInTheDocument();
    expect(screen.getAllByText("Style").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Opening Hours").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AI Basic").length).toBeGreaterThan(0);
    expect(screen.queryByText("Languages")).not.toBeInTheDocument();
    expect(screen.queryByText("Off Days")).not.toBeInTheDocument();
    expect(screen.getAllByText(/tanned yesterday/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("العربية").length).toBeGreaterThan(0);
    expect(screen.getAllByText("You taught").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Price questions → Private DM").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Can you treat this pigmentation/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Write once").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/0 credits/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Auto in every language you select/i).length).toBeGreaterThan(0);
    expect(screen.getByText("One AI app. Every channel. Every customer answered.")).toBeInTheDocument();
    expect(screen.getByText("See what matters. Act faster.")).toBeInTheDocument();
    expect(screen.getByText("Scroll the card to explore")).toBeInTheDocument();
    expect(screen.getAllByText("12,480 remaining").length).toBeGreaterThan(0);
    expect(screen.getAllByText(PUBLIC_SITE.heroTitle).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Download app" }));
    expect(screen.getByRole("menu", { name: "Download Linas AI" })).toBeInTheDocument();
    expect(screen.getAllByText("Download on the App Store").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Get it on Google Play").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Create Account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Log in" })).not.toBeInTheDocument();
    expect(screen.queryByText("login-page")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Page language" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("group", { name: "Download Linas AI" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Contact us" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Explore the app" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Web Chat" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "How it works" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Help & support" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask Linas" })).not.toBeInTheDocument();
  });

  it("keeps privacy/terms/data-deletion footer targets", () => {
    renderLanding("/");

    const privacy = screen.getAllByRole("link", { name: "Privacy Policy" })[0];
    const terms = screen.getAllByRole("link", { name: "Terms of Service" })[0];
    const deletion = screen.getAllByRole("link", { name: "Data Deletion" })[0];
    expect(privacy).toHaveAttribute("href", PUBLIC_PATHS.privacy);
    expect(terms).toHaveAttribute("href", PUBLIC_PATHS.terms);
    expect(deletion).toHaveAttribute("href", PUBLIC_PATHS.dataDeletion);
    expect(screen.getAllByRole("link", { name: /Contact/i })[0]).toBeInTheDocument();
    expect(PUBLIC_SITE.contactEmail).toBe("support@linasai.com");
  });

  it("shows live impact copy", async () => {
    renderLanding("/");
    expect(screen.getByRole("heading", { name: /Every reply/i })).toBeInTheDocument();
    expect(screen.getByText(/Messages answered by Linas/i)).toBeInTheDocument();
    expect(screen.getByText(/Business using Linas/i)).toBeInTheDocument();
    await waitFor(() => {
      const replies = screen.getByText(/Messages answered by Linas/i).closest("div");
      const businesses = screen.getByText(/Business using Linas/i).closest("div");
      expect(replies).toHaveTextContent("12");
      expect(businesses).toHaveTextContent("4");
    });
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
