import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ProtectedRoute from "./components/Auth/ProtectedRoute";
import MobileLiveChat from "./pages/MobileLiveChat";

vi.mock("./pages/LiveChat", () => ({
  /** @param {{ mobile?: boolean }} props */
  default: (props) => (
    <div data-testid="live-chat" data-mobile={props.mobile ? "true" : "false"}>
      LiveChat
    </div>
  ),
}));

const mockUseAuth = vi.fn();
vi.mock("./contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

describe("Mobile live chat auth route", () => {
  it("requires authentication before rendering mobile live chat", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });

    render(
      <MemoryRouter initialEntries={["/mobile/live-chat"]}>
        <Routes>
          <Route path="/login" element={<div>login-page</div>} />
          <Route
            path="/mobile/live-chat"
            element={
              <ProtectedRoute>
                <MobileLiveChat />
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("login-page")).toBeInTheDocument();
    expect(screen.queryByTestId("live-chat")).not.toBeInTheDocument();
  });

  it("renders mobile live chat when authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: { id: "1", role: "operator", resolvedPermissions: { liveChat: true } },
      loading: false,
    });

    render(
      <MemoryRouter initialEntries={["/mobile/live-chat"]}>
        <Routes>
          <Route
            path="/mobile/live-chat"
            element={
              <ProtectedRoute requiredPermission="liveChat">
                <MobileLiveChat />
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    const node = screen.getByTestId("live-chat");
    expect(node).toBeInTheDocument();
    expect(node.getAttribute("data-mobile")).toBe("true");
  });
});
