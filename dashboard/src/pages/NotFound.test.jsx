import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import NotFound from "./NotFound";
import { expectAccessibleControls } from "../testHelpers/a11ySmoke";

describe("NotFound", () => {
  it("shows 404 message and link back to dashboard", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expectAccessibleControls([{ role: "link", name: "Back to Dashboard" }]);
  });
});
