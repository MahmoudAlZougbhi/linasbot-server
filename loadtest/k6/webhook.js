import http from "k6/http";

const base = __ENV.BASE_URL || "";
if (!base || base.includes("linasaibot.com")) {
  throw new Error("refusing to load-test production; set BASE_URL to a staging origin");
}

export const options = {
  scenarios: {
    webhooks: {
      executor: "constant-arrival-rate",
      rate: 5,
      timeUnit: "1s",
      duration: "1m",
      preAllocatedVUs: 10,
    },
  },
};

export default function () {
  http.post(`${base}/api/health`, null, { headers: { "X-Loadtest": "webhook-stub" } });
}
