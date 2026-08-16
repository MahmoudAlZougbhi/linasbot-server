# Exact Python Runtime HA Provisioning

This runbook covers the one-time, two-node installation of the reviewed portable
CPython 3.13 runtime. It does not restart an application service and it does not
download anything from either production node.

## Authority and invariants

Start only from a successful `Quality Gates` run on `main`. Record the exact run
ID, run attempt, target SHA, release artifact ID, artifact REST SHA-256, and
`release-manifest.json` SHA-256. The protected workflow verifies all six values
against GitHub before it transfers any bytes.

The fixed runtime authority is:

- CPython `3.13.15`, pip `26.2.1`, Linux x86-64.
- Archive SHA-256 `aaca2af2ab4d7b68a712660d1334c0cfd5ec13c0312ccd30c29122d8d0342320`.
- Pristine normalized tree SHA-256 `e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc`.
- Executable SHA-256 `ce20f82411f2b0ccdf3e2212ca62303519521d73d25178588f1a9c8d4935c866`.
- libpython SHA-256 `965dcc1afd5934923b5a930e54afcaafc572485394ae33c35d27038bd943dcc5`.
- Canonical runtime path `/opt/linasbot-runtime/cpython-3.13.15`.

Before the first portable-Python process, the workflow uses only
`/usr/bin/python3 -B -I -S`. It authenticates the workflow bridge, release
manifest, control archive and tree, runtime archive, and wheelhouse. The same OS
Python verifies the installed runtime tree, executable, and libpython. Only then
may the trusted launcher execute the canonical runtime.

## Protected workflow

Use `Provision Exact Python Runtime HA` in the protected
`meta-social-cutover` environment. Its concurrency group is the same as all
other Meta HA mutations.

1. Run `plan` (or `dry-run`) with the six exact QG authorities. These operations
   authenticate and plan on the GitHub runner; they do not SSH to production.
2. Save `plan_sha256` and the emitted `APPLY_PYTHON_RUNTIME_...` confirmation.
3. Obtain the required protected-environment approval.
4. Run `apply` with the same six authorities, saved plan SHA, and exact
   confirmation. Do not edit or abbreviate a confirmation.
5. Save the terminal transaction ID, cluster receipt digest, and workflow logs.

The coordinator streams the complete six-file authenticated release, including
`wheelhouse.tar`, `dashboard-build.tar`, and `source.bundle`, to private node02.
Both nodes durably retain, under
`/var/lib/linasbot/meta-ha/python-runtime-transactions/<transaction_id>/`, the
canonical plan, all six release files, and the extracted control tree. Each node
also materializes the same immutable per-artifact global release bundle,
authenticated control tree, and launcher receipt. Recovery therefore does not
depend on GitHub artifact retention or network access.

## Recovery

Run `status` with only the exact transaction ID. It reads durable local authority
and prints the current coordinator digest and the one valid recovery
confirmation. It does not contact GitHub.

Run `recover` with the exact transaction ID, displayed coordinator journal
SHA-256, and displayed confirmation. A durable commit decision is replayed as a
commit. An undecided transaction, or one with a durable rollback decision, is
replayed as rollback. Repeating the exact operation after an SSH ACK loss,
process kill, or reboot is expected and idempotent.

Compensating rollback after a committed install is a separate operation. First
run `status`, then run `rollback` with the exact
`ROLLBACK_COMMITTED_PYTHON_RUNTIME_...` confirmation. The coordinator proves on
both nodes that no bootstrap, deploy, unit, or venv consumes the new runtime
before either node mutates. The new runtime is quarantined; the predecessor and
prior receipts are retained or restored, never deleted.

Do not manually remove active sentinels, coordinator files, transaction
directories, runtime candidates, quarantines, or receipts. Exact recovery owns
their cleanup.

## Durable paths and receipt contract

- Node receipt: `/var/lib/linasbot/meta-ha/python-runtime-provisioned.json`
  (`linas-python-runtime-node-v2`).
- Identical cluster receipt:
  `/var/lib/linasbot/meta-ha/python-runtime-cluster.json`
  (`linas-python-runtime-cluster-v2`).
- Active participant guard:
  `/var/lib/linasbot/meta-ha/python-runtime-provision.active`.
- Coordinator authority on node01:
  `/var/lib/linasbot/meta-ha/python-runtime-provision.coordinator.json`.
- Per-artifact launcher receipt:
  `/var/lib/linasbot/meta-ha/python-runtime-provision-launchers/<artifact_id>-<artifact_api_sha256>.json`.

The v2 node and cluster receipts bind QG repository/workflow/run/attempt/target,
artifact ID and REST digest, manifest digest, the immutable runtime identity,
and these retained wheelhouse fields:
`wheelhouse_archive_sha256`, `wheelhouse_tree_sha256`,
`wheelhouse_file_count`, and `wheelhouse_total_size`. Those QG fields identify
the provisioning transaction; the runtime remains valid for later release
targets whose own bundles are independently authenticated.

## Trusted bootstrap dispatch

Authenticated consumers use this fixed launcher contract on either node:

```text
/usr/bin/python3 -B -I -S <authenticated-launcher> run-bootstrap \
  <transaction-root> <transaction-root>/control <plan-sha256> \
  <bootstrap-command-and-arguments...>
```

`run-bootstrap` verifies the retained transaction authority, v2 receipts, local
node binding, and pristine runtime before executing the fixed authenticated
`scripts.ha.bootstrap_meta_ha_contract` module under canonical Python. It never
imports code from the live checkout.

### Protected Meta HA bootstrap workflow

After runtime provisioning commits on both nodes, use `Bootstrap Protected Meta
HA Contract` from `main`. Every operation shares the `meta-social-cutover`
environment and concurrency lane. Supply the exact runtime transaction ID, runtime
plan digest, QG artifact ID/API digest, and QG target SHA from the committed runtime
receipt; the hash-pinned OS-Python bridge verifies those authorities and the closed
launcher receipt before executing any retained launcher bytes.

Run the operations in this order:

1. `probe` with both exact serving baseline SHAs. Record the emitted PostgreSQL
   state digest.
2. On the owner workstation, change/attest the fixed load balancer's health path
   through `manage_do_lb_ready_healthcheck.py`. Run `install-lb` with strict base64
   of that canonical attestation and its two exact digests.
3. Run `plan` with both baseline SHAs, the probe's PostgreSQL digest, and the LB
   digests. Record the exact bootstrap plan digest and confirmation. The plan
   binds the fixed LB identity, full reviewed `/api/ready` projection, target,
   node probes, and PostgreSQL state; it deliberately excludes the observation
   timestamp and attestation artifact digest.
4. Immediately before `apply`, create a new canonical owner-workstation LB
   attestation for that same projection. Supply its strict base64 and new artifact
   digest directly to the `apply` dispatch, together with the unchanged ready
   projection digest, plan digest, and confirmation. The protected apply run
   installs and validates that evidence before creating its coordinator journal
   or changing service state. A stale observation, different LB/projection/target,
   or any other plan-authority drift fails closed; retry with fresh matching
   evidence without re-planning. Save the committed bootstrap plan digest for the
   release workflow.

If interruption occurs before a durable coordinator decision, run
`rollback-interrupted` with the exact bootstrap transaction ID, plan digest, and
displayed rollback confirmation. If a coordinator journal exists, run
`recovery-status` first and then `recover-decided` with the emitted journal digest
and confirmation. Recovery accepts the older exact target after `main` advances,
but the bridge still requires that target to match the retained runtime plan. Never
delete a bootstrap sentinel, journal, guard, or backup manually.

## Abort conditions

Stop and use `status`; do not improvise if any identity, digest, confirmation,
fixed hostname/private IP, receipt, archive member, tree, or peer acknowledgement
differs. Also stop if any other Meta HA mutation sentinel is present. The
provisioner deliberately shares `/run/lock/linasbot-meta-live.lock` and refuses
overlap with bootstrap, deploy, environment sync, rekey, controlled failover, or
registry-NFS retirement.
