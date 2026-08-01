import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SmartMessaging from "./SmartMessaging";
import { expectAccessibleControls } from "../testHelpers/a11ySmoke";

const authFetchMock = vi.fn();

vi.mock("../utils/authFetch", () => ({
  authFetch: (/** @type {unknown[]} */ ...args) => authFetchMock(...args),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
  },
}));

/** @param {unknown} body @param {boolean} [ok] @param {number} [status] */
function jsonResponse(body, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => body,
  };
}

describe("SmartMessaging preview and approval", () => {
  beforeEach(() => {
    authFetchMock.mockImplementation(async (url) => {
      const path = String(url);
      if (path.includes("/api/smart-messaging/status")) {
        return jsonResponse({ success: true, scheduler_running: true, statistics: {} });
      }
      if (path.includes("/api/smart-messaging/counts")) {
        return jsonResponse({ success: false, error: "Counts backend down" });
      }
      if (path.includes("/api/smart-messaging/templates")) {
        return jsonResponse({ success: true, templates: { reminder_24h: { name: "reminder_24h", ar: "x", en: "y", fr: "z" } } });
      }
      if (path.includes("/api/smart-messaging/settings")) {
        return jsonResponse({ success: true, settings: { previewBeforeSend: true, smartMessagingEnabled: true } });
      }
      if (path.includes("/preview-queue?status=pending_approval")) {
        return jsonResponse({
          success: true,
          messages: [
            {
              message_id: "pending-1",
              customer_name: "Sara",
              customer_phone: "+961111111",
              status: "pending_approval",
              content_preview: "Hello Sara",
            },
          ],
        });
      }
      if (path.includes("/service-mappings")) {
        return jsonResponse({ success: true, mappings: {}, services: [], templates: [] });
      }
      if (path.includes("/template-schedules")) {
        return jsonResponse({ success: true, schedules: {} });
      }
      return jsonResponse({ success: true });
    });
  });

  it("shows em dash counts when counts API fails (not fake zeros)", async () => {
    render(<SmartMessaging />);

    await waitFor(() => {
      expect(screen.getByText("Smart Messaging")).toBeInTheDocument();
    });

    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
    expectAccessibleControls([
      { role: "button", name: "Sent Messages" },
      { role: "button", name: "Message Templates" },
    ]);
  });

  it("loads preview campaign controls on paused and lead tabs", async () => {
    render(<SmartMessaging />);

    await waitFor(() => {
      expect(screen.getByText("Smart Messaging")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Paused (BOC)" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Preview list" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "WhatsApp leads" }));
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "Preview list" }).length).toBeGreaterThan(0);
    });
  });
});
