# Data retention

These jobs are library functions in `services/platform/retention.py`. They are not scheduled on the current droplets.

| Data | Keep |
|---|---|
| `realtime_events` | 24 hours |
| `response_traces` | 30 days |
| `inbound_events` payload bodies | 30 days |
| `inbound_events` ids (idempotency) | 90 days |
| dead-letter queue rows | 30 days |
| per-pod scratch under `/tmp` | deleted when the job finishes |

Cutoffs are arguments, so a rehearsal can use a shorter window. Production scheduling waits until the shared-store flags are on.
