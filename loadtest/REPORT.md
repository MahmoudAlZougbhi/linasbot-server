# Load test report

No staging run was executed. The staging cluster exists, and the token used here cannot download its credentials, so there is no staging URL to send traffic to. These scripts refuse `linasaibot.com`.

## Assumptions

- 100,000 subscribers, 30% daily active, 5% peak concurrent owners: about 500 owner API requests per second and 5,000 SSE connections.
- Customer replies: about 46 per second average and 200 per second at peak.
- Webhooks: about 300 per second at peak, including duplicates.
- Web chat: about 2,000 requests per second at peak.
- Design peak at the edge: about 3,000 requests per second, 200 AI replies per second, 300 webhooks per second, 25,000 SSE connections.

## Measurements

p50, p95, p99, error rate, and queue lag were not measured. Do not treat the targets below as results.

| Target | Bar |
|---|---|
| API p95 / p99, excluding model time | under 300 ms / under 800 ms |
| Webhook acknowledgement p99 | under 200 ms |
| SSE delivery p95 | under 500 ms |
| Error rate | under 0.1% |
| Oldest queued job at peak | under 10 seconds |

## Cost at the 100k design target

Infrastructure only. Model APIs are separate and will dominate at 4 million replies a day.

| | Baseline | Peak |
|---|---|---|
| Estimate | $1,200–2,100 / month | $3,100–5,000 / month |

Starting size, before that target, remains about $110–190 / month.
