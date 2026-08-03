import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ContentManagers from "./ContentManagers";
import { expectAccessibleControls } from "../testHelpers/a11ySmoke";

vi.mock("framer-motion", () => ({
  motion: {
    div: (/** @type {{ children?: import('react').ReactNode } & Record<string, unknown>} */ { children, ...props }) => {
      for (const key of ["initial", "animate", "exit", "transition", "whileHover", "whileTap", "layout"]) {
        delete props[key];
      }
      return <div {...props}>{children}</div>;
    },
  },
  AnimatePresence: (/** @type {{ children?: import('react').ReactNode }} */ { children }) => <>{children}</>,
}));

describe("ContentManagers", () => {
  it("renders landing cards for all CM sections including Dynamic Messages, Restricted, and Publish", () => {
    render(
      <MemoryRouter>
        <ContentManagers />
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Content Managers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Dynamic Messages/i })).toHaveAttribute(
      "href",
      "/content-managers/dynamic-messages"
    );
    expect(screen.getByRole("link", { name: /Restricted/i })).toHaveAttribute(
      "href",
      "/content-managers/restricted"
    );
    expect(screen.getByRole("link", { name: /Preview \/ Validate \/ Publish/i })).toHaveAttribute(
      "href",
      "/content-managers/publish"
    );
    expect(screen.getByRole("link", { name: /AI Basics/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^FAQ/i })).toBeInTheDocument();

    expectAccessibleControls([
      { role: "link", name: /Knowledge/i },
      { role: "link", name: /Prices/i },
    ]);
  });
});
