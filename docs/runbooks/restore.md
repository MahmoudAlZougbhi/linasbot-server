# Restore

Managed Postgres `linas-postgres-prod` already takes a daily backup. Point-in-time recovery is the DigitalOcean default for that backup window (about 7 days).

## Drill

1. Restore into a temporary database `restorecheck_<timestamp>` on the same managed cluster. Do not restore over production.
2. Compare row counts with production at the dump moment.
3. Drop the temporary database.
4. Record the time from "restore started" to "counts matched" (RTO) and the gap between the failure time and the restored time (RPO).

Targets: RPO within 5 minutes, RTO within 60 minutes.

The automated check is `p13-backup.yml`. It has not yet produced a passing restore log.
