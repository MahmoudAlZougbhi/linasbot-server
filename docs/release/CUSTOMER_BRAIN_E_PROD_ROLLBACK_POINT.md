# Customer Brain E — production rollback point

Captured: 2026-09-11 via GitHub Actions **Prod Preflight Readonly** run `34625718445`.

| Field | Value |
|-------|--------|
| Live production SHA | `0f23bcf1d35886acec5dbf53eb1af2faf2734757` |
| Subject | Stop disconnecting Instagram on send-path 190 (#647) |
| Git tag | `rollback/pre-customer-brain-e-production-2026-09-11` |
| Git branch | `rollback/pre-customer-brain-e-prod-live-0f23bcf1` |
| Host (node01) | ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01 |
| App dir | `/opt/linasbot` |
| Rollback path | protected `.github/workflows/deploy.yml` `recover_exact` / redeploy this tag |
| LB | DigitalOcean `2535b8ff-b89c-442b-b5bf-91eae51ed3f6` (`linas-http-lb-lon1`) health `/api/ready` |
| OPENAI_API_KEY on node | PRESENT |
| AUTH_SESSION_SECRET | MISSING (pre-existing; not Brain blocker) |

Do **not** delete this tag, branch, or prior deploy artifacts.
