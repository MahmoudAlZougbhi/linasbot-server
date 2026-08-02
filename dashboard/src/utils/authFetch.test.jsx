import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import authFetch from "./authFetch";

describe("authFetch", () => {
  /** @param {(...args: unknown[]) => Promise<unknown>} impl */
  const mockFetch = (impl) => {
    global.fetch = /** @type {typeof fetch} */ (/** @type {unknown} */ (vi.fn(impl)));
  };

  beforeEach(() => {
    localStorage.setItem("csrf_token", "test-csrf");
    mockFetch(async () => ({
      ok: true,
      json: async () => ({ success: true }),
    }));
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("includes credentials and CSRF header on GET", async () => {
    await authFetch("/api/example");
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/example",
      expect.objectContaining({
        credentials: "include",
        method: "GET",
        headers: expect.objectContaining({ "X-CSRF-Token": "test-csrf" }),
      })
    );
  });

  it("sets JSON Content-Type on POST when body is not FormData", async () => {
    await authFetch("/api/example", {
      method: "POST",
      body: JSON.stringify({ hello: "world" }),
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/example",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-CSRF-Token": "test-csrf",
        }),
      })
    );
  });
});
