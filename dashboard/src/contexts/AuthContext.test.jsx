import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
  },
}));

function AuthProbe() {
  const { user, loading, login, logout } = useAuth();
  if (loading) return <div>auth-loading</div>;
  return (
    <div>
      <div data-testid="user-email">{user?.email || "none"}</div>
      <button
        type="button"
        onClick={() => {
          login("a@test.com", "secret").catch(() => {});
        }}
      >
        login
      </button>
      <button type="button" onClick={() => logout()}>
        logout
      </button>
    </div>
  );
}

function renderAuth(initialRoute = "/") {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>login-page</div>} />
          <Route path="/" element={<AuthProbe />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

/** @param {(...args: unknown[]) => Promise<unknown>} impl */
function mockFetch(impl) {
  global.fetch = /** @type {typeof fetch} */ (/** @type {unknown} */ (vi.fn(impl)));
}

const validSessionUser = {
  id: "1",
  email: "a@test.com",
  role: "admin",
  tenantId: "linas",
  status: "active",
};

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
    mockFetch(async () => ({
      ok: true,
      json: async () => ({ success: false, error: "no session" }),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("clears expired local session older than 24 hours", async () => {
    const stale = {
      user: { id: "1", email: "stale@test.com", role: "admin", tenantId: "linas", status: "active" },
      timestamp: new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString(),
    };
    localStorage.setItem("auth_session", JSON.stringify(stale));

    renderAuth();
    await waitFor(() => {
      expect(screen.getByTestId("user-email")).toHaveTextContent("none");
    });
    expect(localStorage.getItem("auth_session")).toBeNull();
  });

  it("clears invalid backend session response", async () => {
    localStorage.setItem(
      "auth_session",
      JSON.stringify({
        user: { id: "1", email: "a@test.com", role: "admin", tenantId: "linas", status: "active" },
        timestamp: new Date().toISOString(),
      })
    );
    mockFetch(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ success: false, error: "Session expired" }),
    }));

    renderAuth();
    await waitFor(() => {
      expect(screen.getByTestId("user-email")).toHaveTextContent("none");
    });
    expect(localStorage.getItem("auth_session")).toBeNull();
  });

  it("clears session on 401 and does not restore privileged cache", async () => {
    localStorage.setItem(
      "auth_session",
      JSON.stringify({
        user: { id: "1", email: "a@test.com", role: "admin", tenantId: "linas", status: "active" },
        timestamp: new Date().toISOString(),
      })
    );
    mockFetch(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: "Authentication required" }),
    }));

    renderAuth();
    await waitFor(() => {
      expect(screen.getByText("login-page")).toBeInTheDocument();
    });
    expect(localStorage.getItem("auth_session")).toBeNull();
  });

  it("does not restore admin cache on network timeout", async () => {
    localStorage.setItem(
      "auth_session",
      JSON.stringify({
        user: { id: "1", email: "a@test.com", role: "admin", tenantId: "linas", status: "active" },
        timestamp: new Date().toISOString(),
      })
    );
    mockFetch(async () => {
      const err = new Error("Aborted");
      err.name = "AbortError";
      throw err;
    });

    renderAuth();
    await waitFor(() => {
      expect(screen.getByTestId("user-email")).toHaveTextContent("none");
    });
  });

  it("logs in with credentials include and stores csrf token", async () => {
    mockFetch(async (url, options) => {
      if (String(url).includes("/login")) {
        expect(/** @type {RequestInit} */ (options).credentials).toBe("include");
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            csrf_token: "fresh-csrf",
            user: {
              id: "9",
              email: "a@test.com",
              role: "admin",
              tenantId: "linas",
              status: "active",
            },
          }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ success: false }),
      };
    });

    renderAuth();
    await waitFor(() => expect(screen.queryByText("auth-loading")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "login" }));

    await waitFor(() => {
      expect(screen.getByTestId("user-email")).toHaveTextContent("a@test.com");
    });
    expect(localStorage.getItem("csrf_token")).toBe("fresh-csrf");
    expect(localStorage.getItem("auth_session")).toContain("a@test.com");
  });

  it("surfaces login failure for forbidden credentials", async () => {
    mockFetch(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ success: false, error: "Invalid email or password" }),
    }));

    renderAuth();
    await waitFor(() => expect(screen.queryByText("auth-loading")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "login" }));

    await waitFor(() => {
      expect(screen.getByTestId("user-email")).toHaveTextContent("none");
    });
  });

  it("logout clears session storage and navigates to login", async () => {
    localStorage.setItem(
      "auth_session",
      JSON.stringify({
        user: {
          id: "1",
          email: "a@test.com",
          role: "admin",
          tenantId: "linas",
          status: "active",
          resolvedPermissions: {},
        },
        timestamp: new Date().toISOString(),
        lastValidatedAt: new Date().toISOString(),
      })
    );
    localStorage.setItem("csrf_token", "tok");

    mockFetch(async (url) => {
      if (String(url).includes("/session")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            user: { id: "1", email: "a@test.com", role: "admin", tenantId: "linas", status: "active" },
          }),
        };
      }
      if (String(url).includes("/logout")) {
        return { ok: true, status: 200, json: async () => ({ success: true }) };
      }
      return { ok: true, status: 200, json: async () => ({ success: false }) };
    });

    renderAuth();
    await waitFor(() => {
      expect(screen.getByTestId("user-email")).toHaveTextContent("a@test.com");
    });

    fireEvent.click(screen.getByRole("button", { name: "logout" }));

    await waitFor(() => {
      expect(screen.getByText("login-page")).toBeInTheDocument();
    });
    expect(localStorage.getItem("auth_session")).toBeNull();
    expect(localStorage.getItem("csrf_token")).toBeNull();
  });
});
