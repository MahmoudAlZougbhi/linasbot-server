import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Testing from "./Testing";
import { expectAccessibleControls } from "../testHelpers/a11ySmoke";
import { TESTING_LAB_STORAGE_KEY } from "../utils/testingLabSession";

const testMessageWithProvider = vi.fn();

vi.mock("../hooks/useApi", () => ({
  useApi: () => ({
    loading: false,
    testVoiceTranscription: vi.fn(),
    testImageAnalysis: vi.fn(),
    testImageWithUrl: vi.fn(),
    testVoiceWithText: vi.fn(),
    testMessageWithProvider,
    testWebhookSimulation: vi.fn(),
  }),
}));

vi.mock("../utils/authFetch", () => ({
  authFetch: vi.fn(),
}));

/** @returns {HTMLSelectElement} */
function getParitySelect() {
  const selects = screen.getAllByRole("combobox");
  const paritySelect = selects.find(
    (el) =>
      el instanceof HTMLSelectElement &&
      Array.from(el.options).some((opt) => opt.textContent?.includes("Instagram"))
  );
  if (!(paritySelect instanceof HTMLSelectElement)) {
    throw new Error("Expected parity channel select");
  }
  return paritySelect;
}

/** @param {string} message */
async function sendText(message) {
  const input = screen.getByPlaceholderText(/Enter your message here/i);
  fireEvent.change(input, { target: { value: message } });
  const sendButton = screen.getByRole("button", {
    name: /Test Message \(Direct\)/i,
  });
  fireEvent.click(sendButton);
}

describe("Testing Lab social parity", () => {
  beforeEach(() => {
    testMessageWithProvider.mockReset();
    window.localStorage.removeItem(TESTING_LAB_STORAGE_KEY);
    window.localStorage.removeItem("testing_chat_sessions_v1");
  });

  it("exposes Instagram and Facebook channel options with parity labels", async () => {
    render(<Testing />);

    await waitFor(() => {
      expect(screen.getByText("Message Testing")).toBeInTheDocument();
    });

    expect(screen.getByText("Channel (parity)")).toBeInTheDocument();
    const paritySelect = getParitySelect();
    expect(screen.getByRole("option", { name: /Instagram \(Meta social parity\)/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Facebook \(Meta social parity\)/i })).toBeInTheDocument();

    fireEvent.change(paritySelect, { target: { value: "instagram" } });
    expect(
      screen.getByText(/Uses production social processor; Graph send is simulated only/i)
    ).toBeInTheDocument();

    fireEvent.change(paritySelect, { target: { value: "facebook" } });
    expect(
      screen.getByText(/Uses production social processor; Graph send is simulated only/i)
    ).toBeInTheDocument();

    expectAccessibleControls([
      { role: "button", name: "Message Testing" },
      { role: "button", name: "API Testing" },
    ]);
  });

  it("shows first Instagram user + AI messages in Chat View from the same API result", async () => {
    testMessageWithProvider.mockResolvedValue({
      success: true,
      bot_response: "Canonical IG reply",
      simulation: true,
      parity_mode: "meta_social",
      channel: "instagram",
    });

    render(<Testing />);
    fireEvent.change(getParitySelect(), { target: { value: "instagram" } });
    await sendText("LabHelloIG");

    await waitFor(() => {
      expect(testMessageWithProvider).toHaveBeenCalledWith(
        "LabHelloIG",
        "montymobile",
        "123456789",
        "instagram"
      );
    });

    expect(screen.getByRole("button", { name: "Chat View" })).toBeInTheDocument();
    expect(screen.getByText("LabHelloIG")).toBeInTheDocument();
    expect(screen.getByText("Canonical IG reply")).toBeInTheDocument();
    expect(screen.getByText(/montymobile • instagram • 123456789/i)).toBeInTheDocument();
  });

  it("keeps multi-turn order and has no duplicates for Instagram", async () => {
    testMessageWithProvider
      .mockResolvedValueOnce({
        success: true,
        bot_response: "LabReplyOne",
        simulation: true,
        channel: "instagram",
      })
      .mockResolvedValueOnce({
        success: true,
        bot_response: "LabReplyTwo",
        simulation: true,
        channel: "instagram",
      });

    render(<Testing />);
    fireEvent.change(getParitySelect(), { target: { value: "instagram" } });
    await sendText("LabTurnA");
    await waitFor(() => expect(screen.getByText("LabReplyOne")).toBeInTheDocument());
    await sendText("LabTurnB");
    await waitFor(() => expect(screen.getByText("LabReplyTwo")).toBeInTheDocument());

    expect(screen.getByText("LabTurnA")).toBeInTheDocument();
    expect(screen.getByText("LabReplyOne")).toBeInTheDocument();
    expect(screen.getByText("LabTurnB")).toBeInTheDocument();
    expect(screen.getByText("LabReplyTwo")).toBeInTheDocument();
    expect(screen.getAllByText("LabTurnA")).toHaveLength(1);
    expect(screen.getAllByText("LabReplyOne")).toHaveLength(1);
  });

  it("retains the transcript when switching Chat View and Result Cards", async () => {
    testMessageWithProvider.mockResolvedValue({
      success: true,
      bot_response: "SharedLabReply",
      simulation: true,
      channel: "instagram",
    });

    render(<Testing />);
    fireEvent.change(getParitySelect(), { target: { value: "instagram" } });
    await sendText("LabSharedUser");
    await waitFor(() => expect(screen.getByText("SharedLabReply")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Result Cards" }));
    await waitFor(() => {
      expect(screen.getByText("Input:")).toBeInTheDocument();
      expect(screen.getByText("LabSharedUser")).toBeInTheDocument();
      expect(screen.getByText("SharedLabReply")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Chat View" }));
    await waitFor(() => {
      expect(screen.getByText("LabSharedUser")).toBeInTheDocument();
      expect(screen.getByText("SharedLabReply")).toBeInTheDocument();
    });
  });

  it("supports Facebook simulation in Chat View", async () => {
    testMessageWithProvider.mockResolvedValue({
      success: true,
      bot_response: "Canonical FB reply",
      simulation: true,
      channel: "facebook",
    });

    render(<Testing />);
    fireEvent.change(getParitySelect(), { target: { value: "facebook" } });
    await sendText("LabHelloFB");

    await waitFor(() => {
      expect(testMessageWithProvider).toHaveBeenCalledWith(
        "LabHelloFB",
        "montymobile",
        "123456789",
        "facebook"
      );
      expect(screen.getByText("LabHelloFB")).toBeInTheDocument();
      expect(screen.getByText("Canonical FB reply")).toBeInTheDocument();
      expect(screen.getByText(/montymobile • facebook • 123456789/i)).toBeInTheDocument();
    });
  });

  it("clears Chat View and Result Cards together for the active session", async () => {
    testMessageWithProvider.mockResolvedValue({
      success: true,
      bot_response: "Clear me",
      simulation: true,
      channel: "instagram",
    });

    render(<Testing />);
    fireEvent.change(getParitySelect(), { target: { value: "instagram" } });
    await sendText("LabClearUser");
    await waitFor(() => expect(screen.getByText("Clear me")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Clear Chat/i }));
    await waitFor(() => {
      expect(screen.queryByText("LabClearUser")).not.toBeInTheDocument();
      expect(screen.queryByText("Clear me")).not.toBeInTheDocument();
      expect(screen.getByText(/No chat messages yet/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Result Cards" }));
    expect(screen.getByText(/No test results yet/i)).toBeInTheDocument();
  });

  it("shows a failed API response truthfully without inventing a success reply", async () => {
    testMessageWithProvider.mockRejectedValue(new Error("Upstream timeout"));

    render(<Testing />);
    fireEvent.change(getParitySelect(), { target: { value: "instagram" } });
    await sendText("LabFailUser");

    await waitFor(() => {
      expect(screen.getByText("Upstream timeout")).toBeInTheDocument();
    });
    expect(screen.getAllByText("LabFailUser").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Test response received")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Result Cards" }));
    const cardEl = screen.getByText("Upstream timeout").closest(".glass");
    expect(cardEl).toBeInstanceOf(HTMLElement);
    expect(within(/** @type {HTMLElement} */ (cardEl)).getByText("LabFailUser")).toBeInTheDocument();
  });

  it("never claims outbound Meta delivery from the Testing Lab text path", async () => {
    testMessageWithProvider.mockResolvedValue({
      success: true,
      bot_response: "Simulated only",
      simulation: true,
      external_delivery: false,
      channel: "instagram",
    });

    render(<Testing />);
    fireEvent.change(getParitySelect(), { target: { value: "instagram" } });
    await sendText("LabNoOutbound");
    await waitFor(() => expect(screen.getByText("Simulated only")).toBeInTheDocument());

    const firstCall = testMessageWithProvider.mock.calls[0];
    expect(firstCall).toBeTruthy();
    expect(firstCall?.[3]).toBe("instagram");
    expect(testMessageWithProvider).toHaveBeenCalledTimes(1);
  });
});
