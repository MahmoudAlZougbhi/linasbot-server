import React from "react";
import { render, screen } from "@testing-library/react";
import MobileLiveChat from "./MobileLiveChat";

jest.mock("./LiveChat", () => {
  const MockLiveChat = jest.fn(() => <div data-testid="mock-live-chat">LiveChat</div>);
  return {
    __esModule: true,
    default: MockLiveChat,
  };
});

const LiveChat = require("./LiveChat").default;

describe("MobileLiveChat", () => {
  it("renders the shared live chat container in mobile mode", () => {
    render(<MobileLiveChat />);

    expect(screen.getByTestId("mock-live-chat")).toBeInTheDocument();
    expect(LiveChat).toHaveBeenCalledWith(
      expect.objectContaining({ mobile: true }),
      expect.anything()
    );
  });
});
