# Two-node production release policy

## Invariant

An application release may be admitted to production only after the fixed
`node01` and `node02` pair has proved the same tested release SHA, artifact,
runtime environment, and load-balancer readiness contract. The supported entry
point is the protected `.github/workflows/deploy.yml` transaction. It may stage
and activate one node at a time while that node is drained, but it must never
serve a changed node before target parity is durable.

`deploy.sh`, direct per-node helper phases, and every legacy single-node release
path are fail-closed. Preparing an artifact on one node is not admission. A
failed or interrupted transaction must roll both nodes back or leave the
uncertain node or pair drained for confirmed recovery.

## Break glass: disabled by default

The repository does not contain a working single-node release bypass, an enable
flag, an SSH key, or a reusable approval token. `scripts/ha/release_break_glass.sh`
is an intentionally blocked marker so operators get one unambiguous answer.

Emergency access is a separate live control and must require all of the
following before it is temporarily enabled:

1. Two identified people approve a ticket containing the reason, exact target
   SHA, affected nodes, expiry, and rollback owner.
2. The load balancer and both persistent maintenance markers leave both nodes drained
   before any application bytes or service state change.
3. Access uses a short-lived, separately stored credential with MFA and an
   append-only remote audit trail. It expires automatically and is rotated or
   revoked at closeout.
4. A one-node repair stays drained. Production admission remains forbidden until
   the normal `reconcile_exact` or `recover_exact` transaction proves exact
   two-node parity and a fresh load-balancer observation.

Break glass acknowledges that an unrestricted host `root` can bypass host-local
files and services. Product tests prevent supported entrypoints from offering a
single-node release; they do not claim to constrain `root`.

## Required live controls (not provided by this commit)

- Protect `main`, require reviewed pull requests and Quality Gates, add
  `CODEOWNERS` for deployment control files, disable force-push/deletion, and
  apply the rules to administrators.
- Set the `meta-social-cutover` environment to `can_admins_bypass=false`, keep
  self-review disabled, and require an independent release reviewer.
- Disable routine root SSH. Give automation a non-root deploy identity whose
  only privileged command is a root-owned two-node coordinator; restrict the
  node01-to-node02 key to the peer protocol. Keep the separate root credential
  offline or behind time-limited break-glass approval.
- Pin and verify both SSH host identities. Alert on direct changes to
  `/opt/linasbot`, the systemd units, maintenance state, or SSH authorization.
- Add a root-owned service admission check (and readiness check) that rejects a
  local SHA without a durable two-node commit receipt. This protects against
  mistakes by the normal deploy identity; unrestricted root remains the explicit
  break-glass boundary.
