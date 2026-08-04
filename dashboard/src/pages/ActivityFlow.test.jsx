import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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

  it("shows channel, cost summary, and structured detail sections", async () => {
    getFlowLogs.mockResolvedValue({
      success: true,
      data: [
        {
          timestamp: "2026-08-04T12:00:00Z",
          user_id: "...3456",
          user_name: "Test User",
          user_message: "How much is tattoo removal?",
          bot_to_user: "It depends on the area.",
          source: "gpt",
          channel: "whatsapp",
          direction: "inbound",
          handler_path: "ai_orchestration",
          outcome: "answer_question",
          conversation_id: "conv-1",
          model: "gpt-5.4-mini",
          prompt_tokens: 1200,
          completion_tokens: 300,
          tokens: 1500,
          cost_usd: 0.0012,
          input_cost_usd: 0.0003,
          output_cost_usd: 0.0009,
          cost_status: "estimated",
          cost_basis: "openai_usage_tokens_x_configured_rates",
          pipeline_decisions: [{ step: "action", decision: "answer_question" }],
          cm_diagnostics: {
            reason: "packet_ready",
            content_version_id: "cv1",
            source_ids: ["svc.tattoo"],
            retrieved_sources: [{ source_id: "svc.tattoo", title: "Tattoo removal" }],
          },
          flow_steps: [
            { step: 1, title: "User → Bot", content: "How much is tattoo removal?" },
            { step: 2, title: "Bot → User", content: "It depends on the area." },
          ],
        },
      ],
    });

    render(<ActivityFlow />);

    await waitFor(() => {
      expect(screen.getByText("WhatsApp")).toBeInTheDocument();
    });
    expect(screen.getByText("$0.0012")).toBeInTheDocument();

    fireEvent.click(screen.getByText(/How much is tattoo removal/i));

    await waitFor(() => {
      expect(screen.getByText(/Where it went/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/What happened/i)).toBeInTheDocument();
    expect(screen.getByText(/What it read/i)).toBeInTheDocument();
    expect(screen.getByText(/Cost & tokens/i)).toBeInTheDocument();
    expect(screen.getByText(/svc.tattoo/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Show technical JSON/i })).toBeInTheDocument();
  });

  it("shows unavailable cost for historical AI rows without cost", async () => {
    getFlowLogs.mockResolvedValue({
      success: true,
      data: [
        {
          timestamp: "2024-01-01T00:00:00Z",
          user_message: "old message",
          bot_to_user: "old reply",
          source: "gpt",
          channel: "unknown",
          cost_status: "unavailable",
        },
      ],
    });

    render(<ActivityFlow />);
    await waitFor(() => {
      expect(screen.getByText("unavailable")).toBeInTheDocument();
    });
  });
});
