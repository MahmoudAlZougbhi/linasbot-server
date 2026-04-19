import { PATH_TO_PERMISSION } from "./permissions";

describe("live chat permission routes", () => {
  it("keeps desktop live chat mapped to the liveChat permission", () => {
    expect(PATH_TO_PERMISSION["/live-chat"]).toBe("liveChat");
  });

  it("maps the mobile live chat route to the same liveChat permission", () => {
    expect(PATH_TO_PERMISSION["/mobile/live-chat"]).toBe("liveChat");
  });
});
