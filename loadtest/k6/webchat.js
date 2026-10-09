import http from "k6/http";

const base = __ENV.BASE_URL || "";
if (!base || base.includes("linasaibot.com")) {
  throw new Error("refusing to load-test production; set BASE_URL to a staging origin");
}

export const options = {
  scenarios: {
    webchat: {
      executor: "constant-arrival-rate",
      rate: 2,
      timeUnit: "1s",
      duration: "30s",
      preAllocatedVUs: 5,
    },
  },
};

export default function () {
  http.post(`${base}/api/web-chat/session`, JSON.stringify({ widget_key: "staging-fixture" }), {
    headers: { "Content-Type": "application/json" },
  });
}
