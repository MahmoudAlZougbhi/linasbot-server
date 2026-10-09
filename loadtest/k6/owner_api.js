import http from "k6/http";
import { check, sleep } from "k6";

const base = __ENV.BASE_URL || "";
if (!base || base.includes("linasaibot.com")) {
  throw new Error("refusing to load-test production; set BASE_URL to a staging origin");
}

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-arrival-rate",
      startRate: 1,
      timeUnit: "1s",
      preAllocatedVUs: 20,
      stages: [
        { target: 50, duration: "1m" },
        { target: 50, duration: "2m" },
      ],
    },
  },
};

export default function () {
  const response = http.get(`${base}/api/health`);
  check(response, { "200": (item) => item.status === 200 });
  sleep(1);
}
