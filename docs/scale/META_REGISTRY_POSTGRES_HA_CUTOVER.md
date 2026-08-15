# Meta registry Postgres HA cutover and NFS retirement

This runbook is intentionally fail-closed. It does not authorize a production
deployment, database restore, or NFS change. Obtain the task owner's specific
confirmation for each live phase after recording the exact release SHA, node
identities, digest CAS values, backup paths, and rollback commands.

## Authority decision

The read-only production inventory on 2026-08-14 showed that both application
runtimes already resolve the Meta registry backend to Postgres because the
canonical environment omits `META_REGISTRY_BACKEND` and the code default is
`postgres`. Managed Postgres is newer and authoritative (5 bindings / 5
credentials); the legacy NFS file is stale (4 / 4 and older generations/fields).

**Never import the NFS file into the current production Postgres registry.** It
would destroy newer authorization state. `import_meta_registry_to_postgres.py`
exists only for a genuinely empty target or an exceptional, separately approved
restore. Its default dry-run rejects the observed non-empty/divergent shape.

## Phase 0 — immutable evidence and preflight (read-only)

1. Pin one reviewed 40-character release SHA and prove it is the exact clean
   release on node01 and node02 with `verify_meta_release_ha.sh`.
2. Record node private/public identities, systemd working directory/argv,
   canonical environment fingerprint, worker state, nginx config, and absence of
   the legacy service/listener on `:8000`.
3. Change the canonical environment plan so both nodes explicitly contain
   `META_REGISTRY_BACKEND=postgres`; an omitted default is not sufficient for NFS
   retirement.
4. Run `verify_meta_registry_postgres.py` under each node's secure canonical env.
   Record only its counts and deep SHA-256 digests. A stale NFS result is expected
   and is not an import instruction.
5. Confirm Managed Postgres TLS, firewall trusted sources, standby health, backup
   retention/PITR state, schema revision, and the four registry tables. Do not use
   whole-database restore as registry rollback because the database also contains
   unrelated WhatsApp authority.
6. Confirm the load balancer health path is actually `/api/ready`, then prove
   exact `200` + `{"ok": true}` locally and through the LB.

One named operator must hold an exclusive DigitalOcean load-balancer change
window from the first plan/attestation GET through every apply, restore,
failover-phase post-attestation, and final readback or rollback. During that
window nobody may use the DigitalOcean Console, `doctl`, another API client, or
LB automation against this load balancer. DigitalOcean's full-representation
PUT has no conditional ETag/CAS: the required second GET closes known stale-read
interleavings, but it does not eliminate the residual GET-to-PUT provider race.
If exclusive ownership cannot be proved, stop before any LB PUT.

Any mismatch stops the phase. No “skip” flag is permitted.

## Phase 1 — protected four-table backup (live read, no row mutation)

On one verified node, with the canonical environment loaded and a root-only
backup directory, provision a separately generated recovery key in a root-owned
mode `0600` single-purpose file containing only
`CREDENTIAL_REKEY_RECOVERY_KEY=...`.  It must differ from every current or
retained runtime master key and remain on the coordinator/recovery escrow, never
in an application environment.  First dry-run and then create the snapshot only
after live confirmation:

```text
sudo install -d -o root -g root -m 0700 /opt/linasbot_backups/meta-registry

sudo /opt/linasbot/venv/bin/python \
  /opt/linasbot/scripts/ha/meta_registry_pg_snapshot.py \
  snapshot /opt/linasbot_backups/meta-registry/BEFORE.enc \
  --env-file /opt/linasbot/.env \
  --recovery-key-file /var/lib/linasbot/meta-ha/rekey/recovery-key.env

sudo /opt/linasbot/venv/bin/python \
  /opt/linasbot/scripts/ha/meta_registry_pg_snapshot.py \
  snapshot /opt/linasbot_backups/meta-registry/BEFORE.enc \
  --env-file /opt/linasbot/.env \
  --recovery-key-file /var/lib/linasbot/meta-ha/rekey/recovery-key.env \
  --apply
```

The snapshot covers `meta_asset_bindings`, `meta_binding_credentials`,
`meta_oauth_states`, and `meta_registry_audit_events`. It is AES-256-GCM
authenticated with a domain-separated key derived only from the independent
recovery key, atomically created, root-owned mode `0600`, and deeply verified
after write.  A disclosed historical runtime master cannot decrypt this outer
snapshot envelope. Record its digest and protected path. Also record the Managed
Postgres provider backup/PITR checkpoint as defense in depth.

## Phase 2 — identical explicit-Postgres release

Use the transactional two-node deployment procedure. Keep both nodes in durable
maintenance while staging and verifying the exact release and canonical env.
Admit one node only after local release/readiness proof, then the other; finally
prove release/environment parity. Roll back both nodes and their canonical env
from the pre-stage backups if any admission check fails.

Before a node acknowledges staging, the release transaction must fsync every
rollback archive, checksum, environment/runtime preimage, staged tree, and the
transaction directory's parent, then atomically publish and read back a
closed-schema manifest last. Activation and rollback must persist their decision
before each same-filesystem rename, fsync the moved trees and both parent
directories, and publish the next durable manifest only after verifying the
actual artifact digests. A marker or in-memory phase is never sufficient
recovery authority after power loss.

Do not run the file importer. Postgres is already authoritative.

## Phase 3 — HA and functional proof before NFS retirement

With both nodes healthy:

1. Re-run the Postgres verifier on both nodes with the same expected state digest.
2. Prove the LB uses `/api/ready` and drains a maintenance/unready node.
3. Prove node01-down service through node02 and node02-down service through
   node01, including registry reads and writes against Managed Postgres.
4. Exercise Instagram DM, Instagram comments, Facebook DM, and Facebook comments
   with unique evidence IDs. Verify one inbound claim and at most one outbound
   response for each event; replay webhook payloads to prove deduplication.
5. Restore both nodes and re-run exact release, environment, readiness, and
   Postgres registry digest checks.

Keep NFS unchanged through a soak period. A stale NFS file must never be promoted
as rollback authority.

## Phase 4 — NFS retirement (separate destructive/live confirmation)

Do not invoke `remove_registry_nfs.sh` directly; it is an internal per-node
primitive and refuses direct mutation. From fixed node01, run the crash-recoverable
coordinator in read-only plan mode with the exact reviewed release and Postgres
state digests:

```text
sudo /opt/linasbot/venv/bin/python \
  /opt/linasbot/scripts/ha/retire_meta_registry_nfs_ha.py \
  --plan \
  --expected-release-sha <40-hex-release> \
  --expected-pg-sha256 <64-hex-deep-registry-digest>
```

The plan holds the common production lock on both nodes and re-proves exact
release, explicit `postgres`, readiness, node identities, registry invariants,
the active node02 mount, and the active node01 export. It prints a digest-bound
`RETIRE_META_REGISTRY_NFS:<release>:<pg-digest>` token. The operation is
destructive configuration change and must not proceed until the owner gives the
specific live confirmation for that exact token.

NFS retirement accepts only an already-proven authoritative Postgres digest. It
does not invoke the file importer or registry restore, and neither direct
`import_meta_registry_to_postgres.py --apply` nor direct
`meta_registry_pg_snapshot.py restore --apply` is available without a future
signed, current, both-node-drained database-mutation coordinator.

After confirmation, repeat with `--apply --confirm <exact-token>`. The coordinator
creates root-only, fsynced journals on both nodes, binds exact `fstab`, `exports`,
active mount, active export, and filtered postimage digests before mutation, then
retires node02's mount before node01's export. The internal node primitive makes
protected registry tar/config backups, never uses lazy unmount, and retains the
local directories and backups for soak. A later unrelated config edit makes
automatic rollback fail closed instead of overwriting that edit.

If the process, SSH channel, or host stops at any boundary, do not rerun `--apply`
or edit configuration manually. Read the reported journal digest and use only:

```text
--recover --expected-journal-sha256 <digest> \
  --decision forward|rollback \
  --confirm RECOVER_META_REGISTRY_NFS:<tx-id>:<decision>:<digest>
```

A durable commit decision can only move forward. Rollback restores and verifies
the exact journal-bound preimages; a wrong source/type mount, altered export, or
conflicting receipt fails closed. Do not remove the journals, receipts, backups,
or old local registry during this task.

## Registry-only rollback

For a proven registry corruption, dry-run `meta_registry_pg_snapshot.py restore`
against the chosen encrypted snapshot, supplying its independent
`--recovery-key-file`. It prints a snapshot-specific confirmation token. Before
an approved restore, independently record the current four-table digest and
require it with `--expected-current-sha256`. The applied restore also requires
`--expected-release-sha <exact-40-hex-deployed-HEAD>`; it acquires the common
`/run/lock/linasbot-meta-live.lock` first and refuses every active HA transaction
or recovery journal.

Direct `restore --apply` is currently hard-disabled: the local common lock cannot
prove that both nodes have the same release and canonical runtime environment or
that both are drained. A future reviewed two-node coordinator must enforce those
proofs before it may call the transactional restore primitive. The intended
primitive first creates and verifies another encrypted snapshot of the current
target, replaces all four tables in one transaction, and verifies the full
digest; a verification error rolls the database transaction back.

Re-enabling a stale NFS file backend is not a valid rollback. Re-enable only the
NFS mount/export configuration if operationally necessary while keeping
`META_REGISTRY_BACKEND=postgres` and after proving it cannot become authority.

## Hard gate — master-key exposure and cross-product rotation

The read-only node audit found `/opt/linasbot/.env.save` mode `0664` on both nodes
and node02 canonical env/backups owned by uid 501. Those files may contain
`META_CREDENTIAL_ENCRYPTION_KEY`. Before any deploy or backup/restore, inventory
the exact files without printing values, place both nodes in maintenance, and—only
after a specific live confirmation—make every canonical/backup secret file
root-owned mode `0600`. Preserve an encrypted recovery copy and record rollback;
do not delete the insecure files during an unconfirmed step. Permission repair
limits further exposure but cannot undo possible disclosure, so a later key
rotation is required.

`META_CREDENTIAL_ENCRYPTION_KEY` encrypts **both** Meta registry credentials and
`whatsapp_credentials.ciphertext`. Therefore a Meta-only rekey is prohibited: it
would make WhatsApp credentials unreadable. The four-table Meta snapshot is not a
sufficient preimage for master-key rotation because it intentionally excludes the
WhatsApp table. A separately confirmed offline procedure is now implemented in
`scripts/ha/rekey_meta_whatsapp_credentials.py` and documented in
`docs/scale/META_WHATSAPP_CREDENTIAL_REKEY_RUNBOOK.md`; it has not been executed
on production. It must, under one database transaction and with both nodes fully
offline:

1. authenticate/decrypt every Meta and WhatsApp credential with the old key;
2. create an authenticated root-only preimage containing both credential sets,
   encrypted with a new independent recovery key (never the suspected-exposed old
   runtime key), plus provider PITR evidence;
3. require an exact current-target digest, explicit snapshot-specific
   confirmation, and two-node offline/env attestations authenticated by an
   independent transaction proof key and pinned per-node Ed25519 keys rather than
   the old runtime key;
4. re-seal both products with the new key, preserve every AAD/owner/generation,
   decrypt-verify every new envelope, and commit atomically;
5. activate the identical new env on both nodes, restart, and verify Meta plus
   WhatsApp credential reads before LB admission;
6. on any failure, roll back the database transaction or restore the full
   cross-product preimage with the old key, then restore the old env on both nodes.

Do not change the master key as part of the registry NFS cutover.  The independent
recovery key authenticates/decrypts the outer snapshot, but the inner Meta
credential envelopes remain tied to the runtime key that created them. The
snapshot CLI therefore requires `--recovery-key-file`; it also accepts
`--key-env-file` to decrypt-verify an older snapshot's inner credentials. It
**refuses restore when that inner key differs from the current canonical key**:
the Meta ciphertext would require re-sealing and WhatsApp must rotate in the same
transaction. Never delete either required retained key while a snapshot depends
on it; migrate through the separately confirmed cross-product procedure or expire
the snapshot under the retention policy first.
