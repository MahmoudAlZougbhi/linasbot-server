const base = __ENV.BASE_URL || "";
if (!base || base.includes("linasaibot.com")) {
  throw new Error("refusing to load-test production; set BASE_URL to a staging origin");
}

export const options = {
  scenarios: {
    replies: { executor: "constant-arrival-rate", rate: 1, timeUnit: "1s", duration: "30s", preAllocatedVUs: 2 },
  },
};

export default function () {
  // Mock LLM only. Do not point this at production or a live model key.
}
