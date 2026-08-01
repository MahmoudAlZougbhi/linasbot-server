import { afterEach, describe, expect, it } from "vitest";
import { csrfHeaders, getCsrfToken } from "./csrf";

describe("csrf utils", () => {
  afterEach(() => {
    document.cookie = "linas_csrf=; Max-Age=0; path=/";
    localStorage.clear();
  });

  it("reads CSRF token from linas_csrf cookie first", () => {
    document.cookie = "linas_csrf=cookie-token; path=/";
    localStorage.setItem("csrf_token", "storage-token");
    expect(getCsrfToken()).toBe("cookie-token");
    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "cookie-token" });
  });

  it("falls back to localStorage csrf_token when cookie missing", () => {
    localStorage.setItem("csrf_token", "storage-token");
    expect(getCsrfToken()).toBe("storage-token");
  });

  it("returns empty headers when no token is available", () => {
    expect(getCsrfToken()).toBe("");
    expect(csrfHeaders()).toEqual({});
  });
});
