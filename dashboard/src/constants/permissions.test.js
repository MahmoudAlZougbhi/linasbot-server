import { PATH_TO_PERMISSION } from "./permissions";

describe("live chat permission routes", () => {
  it("keeps desktop live chat mapped to the liveChat permission", () => {
    expect(PATH_TO_PERMISSION["/live-chat"]).toBe("liveChat");
  });

  it("does not map obsolete /mobile/live-chat (redirects to get-app)", () => {
    expect(
      /** @type {Record<string, string | undefined>} */ (PATH_TO_PERMISSION)["/mobile/live-chat"]
    ).toBeUndefined();
  });
});

describe("FAQ single entry routes", () => {
  it("maps legacy /training to contentManagers (CM FAQ)", () => {
    expect(PATH_TO_PERMISSION["/training"]).toBe("contentManagers");
  });

  it("maps AI Setup hub to contentManagers", () => {
    expect(PATH_TO_PERMISSION["/content-managers"]).toBe("contentManagers");
  });
});
