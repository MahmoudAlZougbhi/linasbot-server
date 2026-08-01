import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ContentManagers from "./ContentManagers";
import { expectAccessibleControls } from "../testHelpers/a11ySmoke";

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }) => {
      const { initial, animate, exit, transition, whileHover, whileTap, layout, ...rest } = props;
      return <div {...rest}>{children}</div>;
    },
  },
  AnimatePresence: ({ children }) => <>{children}</>,
}));

vi.mock("../components/ContentFilesPanel", () => ({
  default: ({ sectionName }) => <div>content-panel:{sectionName}</div>,
}));
vi.mock("../components/SystemPromptKnowledgeStylePanel", () => ({
  default: () => <div>system-prompt-panel</div>,
}));
vi.mock("../components/DynamicMessagesPanel", () => ({
  default: () => <div>dynamic-messages-panel</div>,
}));

describe("ContentManagers", () => {
  it("renders section tabs and switches panels", async () => {
    render(<ContentManagers />);

    expect(screen.getByRole("heading", { name: "Content Managers" })).toBeInTheDocument();
    expect(screen.getByText("content-panel:Knowledge")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Prices/i }));
    await waitFor(() => {
      expect(screen.getByText("content-panel:Prices")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Dynamic Messages/i }));
    await waitFor(() => {
      expect(screen.getByText("dynamic-messages-panel")).toBeInTheDocument();
    });

    expectAccessibleControls([
      { role: "button", name: "Knowledge" },
      { role: "button", name: "Prices" },
    ]);
  });
});
