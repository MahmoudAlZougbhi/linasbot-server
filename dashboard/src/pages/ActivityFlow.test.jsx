import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ActivityFlow from "./ActivityFlow";

const getFlowLogs = vi.fn();

vi.mock("../hooks/useApi", () => ({
  useApi: () => ({ getFlowLogs }),
}));

describe("ActivityFlow", () => {
  it("renders read-only interaction logs header and empty state on API failure", async () => {
    getFlowLogs.mockResolvedValue({ success: false, error: "Forbidden" });

    render(<ActivityFlow />);

    expect(screen.getByRole("heading", { name: "Interaction Logs" })).toBeInTheDocument();
    expect(
      screen.getByText(/Read-only observability of user ↔ bot ↔ AI turns/i)
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(getFlowLogs).toHaveBeenCalled();
    });
    expect(screen.getByRole("button", { name: /Refresh/i })).toBeInTheDocument();
  });
});
