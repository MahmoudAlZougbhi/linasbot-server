import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeAuthUser } from "../testHelpers/renderWithProviders";
import { ownerPortalRouteElements } from "./OwnerPortalRoutes";

const mockUseAuth = vi.fn();
const portalHostState = { marketing: false };

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));
vi.mock("../pages/portalHost", () => ({
  isMarketingPublicHost: () => portalHostState.marketing,
}));
vi.mock("./api/ownerApi", () => ({
  ownerApi: {
    activationReadiness: () => Promise.resolve({ readiness: { ready_to_enable: false, blockers: [] } }),
    analytics: () => Promise.resolve({ analytics: {} }),
    subscribers: () => Promise.resolve({ subscribers: [] }),
    messageCatalog: () => Promise.resolve({ catalog: { plans: [], topup_packs: [], free: {} } }),
    costs: () => Promise.resolve({ dashboard: {} }),
    messageFlows: () => Promise.resolve({ messages: [] }),
    tenantCosts: () => Promise.resolve({ dashboard: {} }),
    messageLedger: () => Promise.resolve({ ledger: {}, health: {} }),
  },
}));

/** @param {string} path */
function renderOwner(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        {ownerPortalRouteElements()}
        <Route path="/login" element={<div>login-page</div>} />
        <Route path="/app" element={<div>mobile-app-stub</div>} />
        <Route path="/" element={<div>marketing-home</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Owner Portal routes", () => {
  beforeEach(() => {
    portalHostState.marketing = false;
  });

  it("sends anonymous visitors to login", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false, logout: vi.fn() });
    renderOwner("/owner");
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("keeps tenant admins off /owner", () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({ role: "admin", email: "admin@shop.com" }),
      loading: false,
      logout: vi.fn(),
    });
    renderOwner("/owner/users");
    expect(screen.getByText("mobile-app-stub")).toBeInTheDocument();
  });

  it("renders Overview and Users for platform_owner", async () => {
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({ role: "platform_owner", email: "owner@linas.ai" }),
      loading: false,
      logout: vi.fn(),
    });
    const { unmount } = renderOwner("/owner");
    expect(await screen.findByRole("heading", { name: "Owner Portal" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Message flow" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Message catalog" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Costs" })).toBeInTheDocument();
    unmount();
    const users = renderOwner("/owner/users");
    expect(await screen.findByRole("heading", { name: "Owner Portal" })).toBeInTheDocument();
    users.unmount();
    for (const path of ["/owner/messages", "/owner/catalog", "/owner/costs"]) {
      const view = renderOwner(path);
      expect(await screen.findByRole("heading", { name: "Owner Portal" })).toBeInTheDocument();
      view.unmount();
    }
  });

  it("redirects marketing-host /owner to get-app", () => {
    portalHostState.marketing = true;
    mockUseAuth.mockReturnValue({
      user: makeAuthUser({ role: "platform_owner", email: "owner@linas.ai" }),
      loading: false,
      logout: vi.fn(),
    });
    renderOwner("/owner");
    expect(screen.getByText("marketing-home")).toBeInTheDocument();
  });
});
