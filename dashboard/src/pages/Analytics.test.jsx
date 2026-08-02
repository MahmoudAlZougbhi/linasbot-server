import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Analytics from "./Analytics";
import { expectAccessibleControls } from "../testHelpers/a11ySmoke";

const authFetchMock = vi.fn();
vi.mock("../utils/authFetch", () => ({
  authFetch: (/** @type {unknown[]} */ ...args) => authFetchMock(...args),
}));

describe("Analytics", () => {
  beforeEach(() => {
    authFetchMock.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    authFetchMock.mockReturnValue(new Promise(() => {}));
    render(<Analytics />);
    expect(screen.getByText("Loading analytics...")).toBeInTheDocument();
  });

  it("renders success metrics from API data", async () => {
    authFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          overview: {
            total_messages: 1200,
            avg_messages_per_day: 40,
            total_users: 88,
            new_users: 5,
            lifetime_unique_users: 500,
          },
          daily_summaries: [],
          hourly_distribution: {},
          demographics: {},
          sentiment_distribution: {},
          services: {},
          appointments: {},
          satisfaction: {},
          session_ratings: {},
          pause_cleared_resumes: {},
          smart_reminders: {},
          appointment_reschedules_detail: {},
          escalations: {},
          performance: {},
          token_usage: { total_cost_usd: 1.23, total_tokens: 9000, source: "openai_api" },
          conversions: {},
          new_clients: {},
          services_discussed_today: {},
        },
      }),
    });

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByText("Analytics Dashboard")).toBeInTheDocument();
    });
    expect(screen.getByText("1,200")).toBeInTheDocument();
    expectAccessibleControls([
      { role: "button", name: "Refresh" },
      { role: "combobox" },
    ]);
  });

  it("shows empty/zero metrics honestly on successful empty payload", async () => {
    authFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          overview: { total_messages: 0, avg_messages_per_day: 0, total_users: 0, new_users: 0 },
          daily_summaries: [],
          hourly_distribution: {},
          demographics: { languages: { counts: {} }, genders: { counts: {} } },
          sentiment_distribution: { positive: 0, neutral: 0, negative: 0 },
          services: { most_requested: [], most_booked: [] },
          appointments: {},
          satisfaction: { satisfaction_rate: 0, likes: 0, dislikes: 0, dislike_reasons: {} },
          session_ratings: { total_ratings: 0, unique_raters: 0, by_star: {}, percentages: {} },
          pause_cleared_resumes: { recent: [] },
          smart_reminders: { no_response_recent: [], reminder_replies_recent: [] },
          appointment_reschedules_detail: { recent: [] },
          escalations: {},
          performance: {},
          token_usage: { total_cost_usd: 0, total_tokens: 0 },
          conversions: {},
          new_clients: { booked_details: [], asked_not_booked_details: [] },
          services_discussed_today: {},
        },
      }),
    });

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByText("Analytics Dashboard")).toBeInTheDocument();
    });
    expect(screen.queryByText("Unable to load analytics")).not.toBeInTheDocument();
    expect(screen.getByText("No sentiment labels in this period.")).toBeInTheDocument();
  });

  it("shows error UI instead of dashboard zeros when API fails", async () => {
    authFetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ success: false, error: "Analytics unavailable" }),
    });

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByText("Unable to load analytics")).toBeInTheDocument();
    });
    expect(screen.getByText("Analytics request failed (503)")).toBeInTheDocument();
    expect(screen.queryByText("Analytics Dashboard")).not.toBeInTheDocument();
    expect(screen.queryByText("Total Messages")).not.toBeInTheDocument();
    expectAccessibleControls([{ role: "button", name: "Retry" }]);
  });

  it("shows error UI when success flag is false", async () => {
    authFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: false, error: "Firestore quota exceeded" }),
    });

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByText("Unable to load analytics")).toBeInTheDocument();
    });
    expect(screen.getByText("Firestore quota exceeded")).toBeInTheDocument();
    expect(screen.queryByText("Analytics Dashboard")).not.toBeInTheDocument();
  });
});
