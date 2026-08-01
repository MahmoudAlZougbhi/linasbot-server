import { screen } from "@testing-library/react";

/**
 * Lightweight a11y smoke checks using Testing Library role/label queries.
 * Returns missing queries for actionable test failures.
 *
 * @param {Array<{ role: string, name?: string | RegExp, options?: Record<string, unknown> }>} checks
 */
export function expectAccessibleControls(checks) {
  const missing = [];
  for (const check of checks) {
    const { role, name, options } = check;
    try {
      if (name) {
        screen.getByRole(role, { name, ...(options || {}) });
      } else {
        screen.getByRole(role, options);
      }
    } catch {
      missing.push(role + (name ? `: ${name}` : ""));
    }
  }
  if (missing.length) {
    throw new Error(`Missing accessible controls: ${missing.join(", ")}`);
  }
}

/**
 * @param {string} role
 * @param {string | RegExp | undefined} [name]
 * @param {Record<string, unknown> | undefined} [options]
 */
export function queryAccessibleControl(role, name, options) {
  return name
    ? screen.queryByRole(role, { name, ...(options || {}) })
    : screen.queryByRole(role, options);
}
