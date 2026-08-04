import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, Navigate } from "react-router-dom";
import { describe, expect, it } from "vitest";
import NotFound from "./pages/NotFound";

function TestRoutes() {
  return (
    <Routes>
      <Route path="/app" element={<div>dashboard-app</div>} />
      <Route path="/analytics" element={<Navigate to="/app" replace />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

describe("App analytics redirect route", () => {
  it("redirects /analytics to dashboard app home", () => {
    render(
      <MemoryRouter initialEntries={["/analytics"]}>
        <TestRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("dashboard-app")).toBeInTheDocument();
  });

  it("shows NotFound for unknown routes", () => {
    render(
      <MemoryRouter initialEntries={["/does-not-exist"]}>
        <TestRoutes />
      </MemoryRouter>
    );
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
