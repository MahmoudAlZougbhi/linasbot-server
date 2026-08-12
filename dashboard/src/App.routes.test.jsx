import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, Navigate } from "react-router-dom";
import { describe, expect, it } from "vitest";
import NotFound from "./pages/NotFound";

function TestRoutes() {
  return (
    <Routes>
      <Route path="/" element={<div>landing-home</div>} />
      <Route path="/app" element={<div>dashboard-app</div>} />
      <Route path="/analytics" element={<Navigate to="/app" replace />} />
      <Route path="/mobile/live-chat" element={<Navigate to="/#get-app" replace />} />
      <Route path="/live-chat" element={<Navigate to="/#get-app" replace />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

describe("App obsolete operator redirects", () => {
  it("redirects /analytics to dashboard app home", () => {
    render(
      <MemoryRouter initialEntries={["/analytics"]}>
        <TestRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("dashboard-app")).toBeInTheDocument();
  });

  it("redirects /mobile/live-chat to get-app like other obsolete operator paths", () => {
    render(
      <MemoryRouter initialEntries={["/mobile/live-chat"]}>
        <TestRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("landing-home")).toBeInTheDocument();
  });

  it("redirects /live-chat to get-app", () => {
    render(
      <MemoryRouter initialEntries={["/live-chat"]}>
        <TestRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("landing-home")).toBeInTheDocument();
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
