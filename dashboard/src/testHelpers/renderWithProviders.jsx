import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

/**
 * @param {import('react').ReactElement} ui
 * @param {{ route?: string } & Record<string, unknown>} [options]
 */
export function renderWithRouter(ui, { route = "/", ...options } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>,
    options
  );
}

/**
 * @param {Partial<AuthUser>} [overrides]
 * @returns {AuthUser}
 */
export function makeAuthUser(overrides = {}) {
  return {
    id: "user-1",
    email: "operator@example.com",
    name: "Operator",
    role: "operator",
    status: "active",
    permissions: null,
    resolvedPermissions: {
      dashboard: true,
      liveChat: true,
      training: false,
      testing: false,
      analytics: true,
      smartMessaging: true,
      settings: false,
      userManagement: false,
      contentManagers: false,
      contentPublish: false,
      activityFlow: true,
    },
    ...overrides,
  };
}

/**
 * @param {Record<string, { ok?: boolean, status?: number, body?: unknown } | ((url: RequestInfo | URL, options?: RequestInit) => unknown)>} responsesByUrl
 */
export function mockFetchJson(responsesByUrl) {
  return vi.fn(async (url, options = {}) => {
    const key = Object.keys(responsesByUrl).find((k) => String(url).includes(k));
    if (!key) {
      return {
        ok: false,
        status: 404,
        json: async () => ({ success: false, error: `Unmocked fetch: ${url}` }),
      };
    }
    const spec = responsesByUrl[key];
    if (!spec) {
      return {
        ok: false,
        status: 404,
        json: async () => ({ success: false, error: `Unmocked fetch: ${url}` }),
      };
    }
    if (spec === undefined) {
      return {
        ok: false,
        status: 404,
        json: async () => ({ success: false, error: `Unmocked fetch: ${url}` }),
      };
    }
    if (typeof spec === "function") {
      return spec(url, options);
    }
    return {
      ok: spec.ok !== false,
      status: spec.status ?? (spec.ok === false ? 500 : 200),
      json: async () => spec.body,
    };
  });
}
