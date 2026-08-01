import React from "react";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import "@testing-library/jest-dom";

vi.mock("./LiveChat", () => {
  return {
    __esModule: true,
    default: function MockLiveChat(props) {
      return React.createElement(
        "div",
        { "data-testid": "mock-live-chat", "data-mobile": props.mobile ? "true" : "false" },
        "LiveChat"
      );
    },
  };
});

import MobileLiveChat from "./MobileLiveChat";

describe("MobileLiveChat", () => {
  it("renders the shared live chat container in mobile mode", () => {
    render(React.createElement(MobileLiveChat));
    const node = screen.getByTestId("mock-live-chat");
    expect(node).toBeTruthy();
    expect(node.getAttribute("data-mobile")).toBe("true");
  });
});
