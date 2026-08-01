import React from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

export function renderWithRouter(ui, { route = "/", ...options } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>,
    options
  );
}

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
      activityFlow: true,
    },
    ...overrides,
  };
}

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
