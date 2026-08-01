import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Testing from "./Testing";
import { expectAccessibleControls } from "../testHelpers/a11ySmoke";

vi.mock("../hooks/useApi", () => ({
  useApi: () => ({
    loading: false,
    testVoiceTranscription: vi.fn(),
    testImageAnalysis: vi.fn(),
    testImageWithUrl: vi.fn(),
    testVoiceWithText: vi.fn(),
    testMessageWithProvider: vi.fn(),
    testWebhookSimulation: vi.fn(),
  }),
}));

vi.mock("../utils/authFetch", () => ({
  authFetch: vi.fn(),
}));

describe("Testing Lab social parity", () => {
  it("exposes Instagram and Facebook channel options with parity labels", async () => {
    render(<Testing />);

    await waitFor(() => {
      expect(screen.getByText("Message Testing")).toBeInTheDocument();
    });

    expect(screen.getByText("Channel (parity)")).toBeInTheDocument();
    const selects = screen.getAllByRole("combobox");
    const paritySelect = selects.find((el) =>
      Array.from(el.options).some((opt) => opt.textContent.includes("Instagram"))
    );
    expect(paritySelect).toBeTruthy();
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
});
