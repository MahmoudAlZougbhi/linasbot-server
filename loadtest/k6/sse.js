const base = __ENV.BASE_URL || "";
if (!base || base.includes("linasaibot.com")) {
  throw new Error("refusing to load-test production; set BASE_URL to a staging origin");
}

export const options = {
  scenarios: {
    sse: { executor: "constant-vus", vus: 5, duration: "30s" },
  },
};

export default function () {
  // Staging only. A real run needs xk6-sse and a staging session token.
}
