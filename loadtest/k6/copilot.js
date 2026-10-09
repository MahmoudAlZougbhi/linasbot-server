const base = __ENV.BASE_URL || "";
if (!base || base.includes("linasaibot.com")) {
  throw new Error("refusing to load-test production; set BASE_URL to a staging origin");
}

export const options = {
  scenarios: {
    copilot: { executor: "constant-arrival-rate", rate: 1, timeUnit: "1m", duration: "1m", preAllocatedVUs: 1 },
  },
};

export default function () {
  // About 20 turns per minute belongs on staging with a mock provider.
}
