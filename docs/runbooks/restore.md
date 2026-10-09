# Restore

Managed Postgres `linas-postgres-prod` already takes a daily backup. Point-in-time recovery is the DigitalOcean default for that backup window (about 7 days). Staging has its own cluster, `linas-staging-pg`.

## Drill

1. In the DigitalOcean control panel, restore the chosen backup or PITR time to a **new** cluster. Do not restore over production.
2. Point a staging app setting at that new cluster. Do not change production `DATABASE_URL`.
3. Run the local foundation checks in `tests/e2e_cluster/`.
4. Record the time from "restore started" to "checks passed" (RTO) and the gap between the failure time and the restored time (RPO).
5. Delete the drill cluster.

Targets: RPO within 5 minutes, RTO within 60 minutes.

This drill has not been run. The current token cannot download the staging cluster credentials, so staging cannot be pointed at a restored cluster from here.
