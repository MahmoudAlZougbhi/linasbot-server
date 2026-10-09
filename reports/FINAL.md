# Final report

Production is still served by the two droplets. `https://linasaibot.com/api/health` returned 200 at the start of this step. The Kubernetes cluster `linas-prod-doks` is running, and this token cannot download its credentials (403). No traffic was moved. DNS was not changed. Secrets were not rotated. Droplet workers were not stopped. QA rows were not deleted.

## What shipped in code

- Android purchase calls Play Billing when the native module is present, then `POST /api/entitlements/google/verify`. Without Play credentials that endpoint returns 503 and grants nothing.
- The Copilot stream shows a between-low-and-high sentence when the server sends that range.
- The dashboard has plan and purchased cards.
- `scripts/ops/cleanup_linas_qa_leftovers.py` dry-run refuses `--execute` without a backup. It was not run against production.
- `scripts/ops/health_poll.sh` polls health every 2 seconds.

## Not done

The cutover, the 3-day shadow diff, the production deploy, the APK, Play internal, and TestFlight were not completed. Support MX was not changed. TikTok was not disconnected. The junk price rows were not edited.
