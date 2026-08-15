# Meta + WhatsApp credential master-key rotation

Status: prepared and locally tested; **not executed on production**.

`META_CREDENTIAL_ENCRYPTION_KEY` encrypts two independent products:

- every row in `meta_binding_credentials.sealed`; and
- every row in `whatsapp_credentials.ciphertext`.

Rotating only one table, changing either node's environment early, or restoring
only the Meta four-table snapshot would make live credentials unreadable.  Use
`scripts/ha/rekey_meta_whatsapp_credentials.py` only as the single
cross-product procedure below.

## Non-negotiable gates

Do not begin the live window until all of these are true:

1. The owner has specifically approved this live key rotation and its maintenance
   window.  Approval for the registry NFS cutover is not approval for a master-key
   rotation.
2. `node01` and `node02` run the same reviewed release.  Both canonical env files
   are root-owned `0600`; both declare `META_REGISTRY_BACKEND=postgres`, fixed
   `META_DELETION_NODE_ID`, and exact membership `node01,node02`.
3. The DigitalOcean load balancer's direct port-8003 health check is exactly
   `/api/ready`, and `META_HA_LB_READY_HEALTHCHECK_APPROVED=true` is present only
   after that external state was read back.
   One named operator must exclusively own the LB from the first attestation GET
   through all drain/admission post-attestations and final readback/rollback; no
   Console, `doctl`, other API client, or automation may mutate it in that
   interval. The provider exposes no conditional PUT CAS, so double reads reduce
   but do not remove the final GET-to-PUT race.
4. A fresh Managed PostgreSQL provider backup/PITR timestamp is recorded.  PITR is
   a second recovery layer; it does not replace the table-specific encrypted
   preimage created below.
5. The legacy `linas_ai_bot.service`/port `8000`, `linasbot.service`/port `8003`,
   and all four `linasbot-worker@...` units can be stopped on both nodes.  The
   tool refuses an offline proof if either port is listening or any unit is active.
6. A new runtime key, a recovery key, and a transaction proof key exist as
   separate root-only `0600` files.  They must be generated independently and
   must all differ from each other and from the old runtime key.  The recovery
   key file contains only:

   ```dotenv
   CREDENTIAL_REKEY_RECOVERY_KEY=<independent high-entropy recovery secret>
   ```

   The new runtime-key file contains only:

   ```dotenv
   META_CREDENTIAL_ENCRYPTION_KEY=<new high-entropy runtime secret>
   ```

   The transaction proof-key file contains only:

   ```dotenv
   CREDENTIAL_REKEY_PROOF_KEY=<independent high-entropy transaction proof secret>
   ```

   The independent recovery key is mandatory.  The historical old runtime key may
   have been exposed by `.env.save`; using it to encrypt the outer preimage would
   not keep that preimage confidential.
7. Each node has its own Ed25519 attestation private key in a root-only `0600`
   single-purpose file containing only
   `CREDENTIAL_REKEY_NODE_SIGNING_KEY=<unpadded-url-safe-base64-32-bytes>`.  A
   pinned verification manifest, identical on the coordinator and both nodes,
   contains exactly `CREDENTIAL_REKEY_NODE01_VERIFY_KEY=...` and
   `CREDENTIAL_REKEY_NODE02_VERIFY_KEY=...`.  The two public keys must differ;
   record and review the manifest SHA-256.  The node02 private key must never be
   copied to node01/coordinator (and vice versa).  The shared transaction proof
   key is therefore insufficient to forge the peer's proof.
8. The new runtime-key, proof-key, and public verification manifest are staged
   securely and identically on both nodes.  The proof key authenticates only this
   transaction's offline/env attestations; it never encrypts credentials or
   backups.  Remove its node copies after guard release and retain the original
   only in recovery escrow while its signed env-backup attestations are retained.
   A rollback uses a fresh proof key.  Node signing keys remain node-local.  The
   recovery key and encrypted database preimage remain only on the coordinator
   and approved recovery escrow; the recovery key is never distributed to either
   app runtime.
9. The static systemd guard contract has been separately installed and verified
   on both healthy nodes by Phase 0.  Do not first discover a missing or unloaded
   drop-in after both nodes have been drained and stopped.

The attestation contract pins the exact `/opt/linasbot/.env` path, reviewed
hostname, public/private IPs, machine-id digest, node-specific signature, exact
systemd guard, transaction ID, and env-backup digest.  It protects against a
copied env or a leaked old runtime key being used to fabricate the peer.  An
active root compromise can replace code, keys, systemd state, and host identity
and is outside what an in-process proof can defend; stop and rebuild that node
from trusted infrastructure if root integrity is in doubt.

Every output directory used below must already be root-owned mode `0700`.  Every
proof, env backup, and encrypted preimage is created without overwriting an
existing file and is verified as root-owned mode `0600`.

## Phase 0 — pre-provision the static boot guard while healthy

Complete this phase on both nodes before arming maintenance or stopping any
service.  First run the default dry-run locally and record its exact
`INSTALL_REKEY_GUARD_CONTRACT_...` token:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  guard-contract \
  --env-file /opt/linasbot/.env \
  --node-id <node01-or-node02>
```

After the owner separately approves that node's token, install the reviewed
contract:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  guard-contract --apply \
  --env-file /opt/linasbot/.env \
  --node-id <node01-or-node02> \
  --confirm <exact-INSTALL_REKEY_GUARD_CONTRACT-token>
```

The command installs the exact packaged
`deploy/systemd/95-linasbot-credential-rekey-guard.conf` content for the API,
worker template, and legacy API, reloads systemd, and confirms every canonical
unit reports the drop-in as loaded.  The transaction marker does not exist in
this phase, so the negated condition remains true: running processes are
untouched and normal manual/boot starts remain allowed.  A crash after any
partial prefix is safe and rerunnable because no transaction marker is
published.

Run this read-only preflight on each node immediately before scheduling the
maintenance window:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  guard-contract --verify-only \
  --env-file /opt/linasbot/.env \
  --node-id <node01-or-node02>
```

Both checks must print the same static contract SHA-256.  If a file is absent,
changed, not loaded, or a transaction marker already exists, stop here while the
cluster is still healthy.  The static drop-ins remain installed across future
rekeys; only the root-private transaction marker arms or releases them.

## Phase 1 — read-only plan

Choose one 32-character lowercase hexadecimal transaction ID and one new
WhatsApp key-version label (for example `rotation-20260814-01`).  Reuse that
transaction ID through successful env activation; use a new transaction ID for
a later rollback attempt.

On the coordinator, run the default dry-run:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  rekey \
  --env-file /opt/linasbot/.env \
  --new-key-file /var/lib/linasbot/meta-ha/rekey/new-runtime-key.env \
  --recovery-key-file /var/lib/linasbot/meta-ha/rekey/recovery-key.env \
  --proof-key-file /var/lib/linasbot/meta-ha/rekey/transaction-proof-key.env \
  --node-signing-key-file /var/lib/linasbot/meta-ha/rekey/node01.signing-key.env \
  --node-verification-keys-file /var/lib/linasbot/meta-ha/rekey/node-verification-keys.env \
  --database-certificate /var/lib/linasbot/meta-ha/rekey/rekey-database-certificate.json \
  --new-key-version rotation-20260814-01 \
  --transaction-id <transaction-id>
```

The dry-run takes the database advisory locks plus fail-fast PostgreSQL `SHARE`
locks across all four owner/credential tables, inventories both products,
decrypts every credential with the old key, re-seals and re-opens every payload
in memory with the new key, and prints only counts, a full CAS digest, and the
exact confirmation token.  It performs no write.

Stop if the inventory is partial, a ciphertext is invalid, the effective registry
backend is `file`, `dual`, or implicit, the database is not PostgreSQL, or either
key file fails its security contract.

## Phase 2 — persistent drain and exact env backups

Arm `/var/lib/linasbot/meta-ha/maintenance` on both nodes, wait until both LB
members are unhealthy, then stop the API, legacy API, and four workers on both
nodes.  Confirm ports `8000` and `8003` are closed.  Do not clear maintenance if
any later step fails.

Run `offline-proof` without `--apply` locally on each node and record its exact
`ARM_REKEY_GUARD_...` confirmation.  Then run the apply form below with that
node's token and node-local private signing key.  Use node-specific output paths:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  offline-proof --apply \
  --env-file /opt/linasbot/.env \
  --proof-key-file /var/lib/linasbot/meta-ha/rekey/transaction-proof-key.env \
  --node-signing-key-file /var/lib/linasbot/meta-ha/rekey/<node>.signing-key.env \
  --node-verification-keys-file /var/lib/linasbot/meta-ha/rekey/node-verification-keys.env \
  --env-backup /var/lib/linasbot/meta-ha/rekey/<node>.env.before \
  --output /var/lib/linasbot/meta-ha/rekey/<node>.offline-proof.json \
  --node-id <node01-or-node02> \
  --transaction-id <transaction-id> \
  --confirm <exact-ARM_REKEY_GUARD-token>
```

Copy the node02 proof—not its env backup—to the coordinator over the existing
root SSH channel.  Each proof has both the independent transaction HMAC and its
node-specific Ed25519 signature, never the suspected-exposed old runtime key.
Before signing, the apply command revalidates every preloaded static drop-in and
then atomically publishes one root-private transaction marker.  It never installs
individual drop-ins or reloads systemd inside the maintenance window.  Reboot or
`systemctl start` stays blocked until a separately confirmed `release-guard`.
Each proof is initially valid for five minutes and attests the exact backup
digest, fixed physical node identity, PostgreSQL authority, `/api/ready`
approval, persistent maintenance, six stopped units, both closed ports, and the
loaded guard digest.  Database apply must begin while both are fresh.  Its
durable signed database certificate then binds their exact files for crash-safe
continuation without extending standalone freshness.

If a node process dies after the marker or exact env backup is fsynced but before
the proof is written, rerun with the same transaction and backup path plus an
unused proof output path.  An existing backup is accepted only when its protected
bytes exactly equal the still-canonical env; a mismatch fails closed.  Never
delete or replace the backup to make a retry pass.

## Phase 3 — one database transaction

Repeat the dry-run after the proofs exist.  The digest must still equal Phase 1.
Only after the owner confirms the printed token, run:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  rekey --apply \
  --env-file /opt/linasbot/.env \
  --new-key-file /var/lib/linasbot/meta-ha/rekey/new-runtime-key.env \
  --recovery-key-file /var/lib/linasbot/meta-ha/rekey/recovery-key.env \
  --proof-key-file /var/lib/linasbot/meta-ha/rekey/transaction-proof-key.env \
  --node-signing-key-file /var/lib/linasbot/meta-ha/rekey/node01.signing-key.env \
  --node-verification-keys-file /var/lib/linasbot/meta-ha/rekey/node-verification-keys.env \
  --database-certificate /var/lib/linasbot/meta-ha/rekey/rekey-database-certificate.json \
  --new-key-version rotation-20260814-01 \
  --transaction-id <transaction-id> \
  --node-proof /var/lib/linasbot/meta-ha/rekey/node01.offline-proof.json \
  --node-proof /var/lib/linasbot/meta-ha/rekey/node02.offline-proof.json \
  --local-env-backup /var/lib/linasbot/meta-ha/rekey/node01.env.before \
  --preimage /var/lib/linasbot/meta-ha/rekey/all-credentials.before.enc \
  --expected-current-sha256 <phase-1-full-sha256> \
  --confirm <exact-dry-run-confirmation-token>
```

The apply path:

1. takes the common application lock, a fail-fast global rekey advisory lock, the
   normal Meta registry advisory lock, and fail-fast PostgreSQL
   `ACCESS EXCLUSIVE ... NOWAIT` locks on both owner and credential tables;
2. repeats the full CAS inventory and validates all Meta/WhatsApp relationships;
3. writes and authenticates the independent-key-encrypted cross-product preimage,
   then fsyncs a node01-signed source/target certificate before the first SQL update;
4. decrypts every old envelope, preserves each exact Meta AAD and derived
   WhatsApp AAD, re-seals with the new key, and CAS-updates every row;
5. preserves owners, generations, timestamps, scopes, expiry/revocation state,
   and all non-ciphertext fields;
6. reloads all rows, compares the structural digest and plaintext semantic digest,
   and decrypts every new envelope before the transaction can commit.

Any exception before commit rolls back both products.  If the process dies after
certificate preparation or commit, rerun the exact reviewed release, transaction
ID, keys, proofs, preimage, and certificate path.  The retry-stable target resumes
only an exact certified source, finalizes an exact certified target, and fails
closed for anything else.  Never delete or rename a prepared certificate to force
a retry, guess which key is active, or start one node during reconciliation.
Copy the signed database certificate (but never the recovery key or encrypted
preimage) to node02 over the root SSH channel and compare its SHA-256 on both
nodes before Phase 4.  Also place the exact two signed offline-proof files on
each node; do not copy either node's env backup or private signing key to its
peer.

## Phase 4 — stage the new env on both offline nodes

After Phase 3 the database uses the new key while both canonical envs still use
the old key.  This split state is expected and must stay offline.

Run `stage-env` first as a dry-run, then with its printed confirmation token,
locally on each node.  Each node needs both signed offline proofs:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  stage-env --apply \
  --env-file /opt/linasbot/.env \
  --env-backup /var/lib/linasbot/meta-ha/rekey/<node>.env.before \
  --new-key-file /var/lib/linasbot/meta-ha/rekey/new-runtime-key.env \
  --proof-key-file /var/lib/linasbot/meta-ha/rekey/transaction-proof-key.env \
  --node-signing-key-file /var/lib/linasbot/meta-ha/rekey/<node>.signing-key.env \
  --node-verification-keys-file /var/lib/linasbot/meta-ha/rekey/node-verification-keys.env \
  --database-certificate /var/lib/linasbot/meta-ha/rekey/rekey-database-certificate.json \
  --node-proof /var/lib/linasbot/meta-ha/rekey/<node>.offline-proof.json \
  --peer-node-proof /var/lib/linasbot/meta-ha/rekey/<peer>.offline-proof.json \
  --output /var/lib/linasbot/meta-ha/rekey/<node>.new-env-proof.json \
  --node-id <node01-or-node02> \
  --transaction-id <transaction-id> \
  --expected-database-sha256 <database-rekeyed-sha256> \
  --confirm <exact-stage-env-confirmation-token>
```

This atomically changes only `META_CREDENTIAL_ENCRYPTION_KEY`, verifies every DB
credential with that key, and signs a proof while all services remain stopped.
It never copies node01's local node ID onto node02.

Copy both exact new-env proofs to the coordinator and to each node over the root
channel (never copy private signing keys), then run:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  verify-env \
  --env-file /opt/linasbot/.env \
  --proof-key-file /var/lib/linasbot/meta-ha/rekey/transaction-proof-key.env \
  --node-verification-keys-file /var/lib/linasbot/meta-ha/rekey/node-verification-keys.env \
  --database-certificate /var/lib/linasbot/meta-ha/rekey/rekey-database-certificate.json \
  --env-proof /var/lib/linasbot/meta-ha/rekey/node01.new-env-proof.json \
  --env-proof /var/lib/linasbot/meta-ha/rekey/node02.new-env-proof.json \
  --transaction-id <transaction-id> \
  --expected-database-sha256 <database-rekeyed-sha256>
```

`verify-env` requires both independent node signatures, distinct signed machine
identities, equal keyed fingerprints of all shared `META_*` settings plus the
effective PostgreSQL authority and maintenance path, the same DB digest, and
complete new-key decryptability.  A long pause or reboot after the first node is
staged remains recoverable: the signed proofs are durable only through the exact
database certificate, while each command freshly checks its local env/guard/host
and database.  Do not restart unless `verify-env` prints restart eligibility.

The normal live env synchronizer is deliberately not used during this split-key
interval: it restarts runtime processes as part of activation, while safe rekeying
requires both nodes to remain offline until their key proofs agree.

## Phase 5 — controlled restart and evidence

Keep persistent LB maintenance armed.  The transaction guard still blocks every
API/worker/legacy start.  Run `release-guard` without `--apply` locally on each
node, review each proof/digest/certificate-specific token, then explicitly release
node01 and node02.  A pause or reboot after the first release is recoverable: the
second node accepts the same signed env proofs only through the durable database
certificate and freshly rechecks its own exact env, guard, host, DB, and
decryptability.  Do not start either node between releases in the planned flow:

```bash
sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
  release-guard --apply \
  --env-file /opt/linasbot/.env \
  --proof-key-file /var/lib/linasbot/meta-ha/rekey/transaction-proof-key.env \
  --node-signing-key-file /var/lib/linasbot/meta-ha/rekey/<node>.signing-key.env \
  --node-verification-keys-file /var/lib/linasbot/meta-ha/rekey/node-verification-keys.env \
  --database-certificate /var/lib/linasbot/meta-ha/rekey/rekey-database-certificate.json \
  --env-proof /var/lib/linasbot/meta-ha/rekey/node01.new-env-proof.json \
  --env-proof /var/lib/linasbot/meta-ha/rekey/node02.new-env-proof.json \
  --node-id <this-node> \
  --transaction-id <transaction-id> \
  --expected-database-sha256 <database-rekeyed-sha256> \
  --confirm <exact-RELEASE_REKEY_GUARD-token>
```

This rechecks both node signatures and their certificate binding, DB
digest/decryptability, local guard integrity, stopped units, closed ports, and
persistent LB maintenance.  It durably writes and revalidates a node-signed,
transaction/digest-bound release receipt before atomically removing only the
local marker; static drop-ins remain loaded for future transactions.  A crash
before receipt or marker removal leaves starts blocked.  A crash after receipt
but before marker removal is safely retried, and a retry after marker removal
authenticates the same durable receipt.  Never remove guard or receipt files by
hand.

After both authorized releases complete, start API and workers on node01, prove
liveness and expected readiness `503`, then start the peer and repeat.  Rerun the
complete credential verifier.  Then admit one node at a time by the reviewed HA
procedure:

1. clear that node's maintenance marker;
2. prove direct `/api/ready` is `200` and the LB marks only that node healthy;
3. perform a credential-read smoke for Meta and WhatsApp without provider writes;
4. repeat for the peer and prove both run the identical release/env contract;
5. perform the separate live Facebook/Instagram DM/comment no-duplicate matrix and
   WhatsApp credential smoke already approved for the cutover.

Do not delete the old key, either node's env backup, the encrypted preimage, or the
recovery key while rollback retention remains open.  Old Meta-only snapshots still
depend on the old key and need their own retention/migration decision.

## Rollback

Rollback is also a full maintenance transaction, never a Meta-only restore.

1. Re-arm persistent maintenance, wait for both LB members to drain, stop the six
   units on both nodes, generate and stage a fresh independent rollback proof key,
   and create fresh `offline-proof` files and fresh exact env backups using the
   new rollback transaction ID.  Do not reuse the initial proof key for fresh
   rollback attestations.
2. Run `rollback` without `--apply`; verify the current and target digests and get
   the exact confirmation token.
3. After specific owner confirmation, transactionally restore both credential
   tables:

   ```bash
   sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
     rollback --apply \
     --env-file /opt/linasbot/.env \
     --restored-key-file /var/lib/linasbot/meta-ha/rekey/node01.env.before \
     --recovery-key-file /var/lib/linasbot/meta-ha/rekey/recovery-key.env \
     --proof-key-file /var/lib/linasbot/meta-ha/rekey/rollback-proof-key.env \
     --original-proof-key-file /var/lib/linasbot/meta-ha/rekey/transaction-proof-key.env \
     --original-node-proof /var/lib/linasbot/meta-ha/rekey/node01.offline-proof.json \
     --node-signing-key-file /var/lib/linasbot/meta-ha/rekey/node01.signing-key.env \
     --node-verification-keys-file /var/lib/linasbot/meta-ha/rekey/node-verification-keys.env \
     --database-certificate /var/lib/linasbot/meta-ha/rekey/rollback-database-certificate.json \
     --preimage /var/lib/linasbot/meta-ha/rekey/all-credentials.before.enc \
     --pre-rollback /var/lib/linasbot/meta-ha/rekey/all-credentials.pre-rollback.enc \
     --original-transaction-id <initial-transaction-id> \
     --transaction-id <rollback-transaction-id> \
     --node-proof <fresh-node01-proof> \
     --node-proof <fresh-node02-proof> \
     --expected-current-sha256 <current-full-sha256> \
     --confirm <exact-rollback-confirmation-token>
   ```

   Before any DB mutation, rollback authenticates the retained node01 original
   env backup and node-signed proof with the original proof key, and proves the
   fresh rollback proof key differs.  Restore refuses insert/delete semantics:
   the complete owner/generation
   structure and the decrypted Meta+WhatsApp plaintext semantic digest must still
   match the preimage.  It will not silently overwrite a post-rekey credential
   change.  It creates an independently encrypted snapshot of the current
   new-key state and a durable signed source/target certificate before
   CAS-restoring either product.  A commit failure is resumed or finalized by the
   same exact-source/exact-target state machine used for rekey.
   Copy only the signed rollback certificate to node02 and verify its SHA-256
   parity before restoring either env; keep the recovery key and database
   preimages coordinator-only.
4. Run `restore-env` locally on each node.  It authenticates that node's original
   pre-rekey env backup with the original signed proof, authenticates the fresh
   current-env backup with the fresh proof, verifies the rolled-back DB using the
   old key, then atomically restores the exact node-local env.  Run it dry first and
   supply the printed token only after review:

   ```bash
   sudo /opt/linasbot/venv/bin/python /opt/linasbot/scripts/ha/rekey_meta_whatsapp_credentials.py \
     restore-env --apply \
     --env-file /opt/linasbot/.env \
     --desired-env-backup /var/lib/linasbot/meta-ha/rekey/<node>.env.before \
     --current-env-backup <fresh-current-node-env-backup> \
     --original-node-proof <initial-node-offline-proof> \
     --original-proof-key-file <initial-transaction-proof-key-file> \
     --proof-key-file <fresh-rollback-proof-key-file> \
     --node-signing-key-file <this-node-private-signing-key-file> \
     --node-verification-keys-file <pinned-two-node-verification-key-file> \
     --database-certificate /var/lib/linasbot/meta-ha/rekey/rollback-database-certificate.json \
     --node-proof <fresh-current-node-proof> \
     --peer-node-proof <fresh-current-peer-proof> \
     --output <node-restored-env-proof> \
     --node-id <node01-or-node02> \
     --original-transaction-id <initial-transaction-id> \
     --transaction-id <rollback-transaction-id> \
     --expected-database-sha256 <database-restored-sha256> \
     --confirm <exact-restore-env-confirmation-token>
   ```
5. Collect and distribute the exact two restored-env proofs to the coordinator
   and both nodes, then run `verify-env` against the restored DB digest, passing
   the rollback database certificate.  Run the same separately confirmed
   `release-guard` on both still-offline nodes; the certificate makes a pause
   after the first env restore or guard release recoverable. Restart/admit nodes
   only by Phase 5.

If rollback encounters a changed owner/generation inventory, an unauthenticated
backup, a CAS mismatch, or one node cannot restore its exact env, leave both nodes
offline and preserve every artifact.  Recover into a new Managed PostgreSQL
cluster from provider PITR or escalate for a separately reviewed reconciliation;
do not force, truncate, import stale NFS, or mix old/new keys.

## Required live confirmations

This runbook intentionally separates confirmations:

- permission repair/archive of historical env backups;
- provider PITR/fork creation (cost-bearing live infrastructure);
- each node's `INSTALL_REKEY_GUARD_CONTRACT_...` static systemd contract change,
  completed while that node is healthy and before the maintenance window;
- stopping both nodes and legacy `:8000` for the maintenance window;
- each node's `ARM_REKEY_GUARD_...` atomic transaction-marker publication;
- the digest-specific `REKEY_META_WHATSAPP_...` database mutation;
- each node's `STAGE_REKEY_ENV_...` environment replacement;
- each node's `RELEASE_REKEY_GUARD_...` controlled-start eligibility;
- any `ROLLBACK_META_WHATSAPP_...` and `RESTORE_REKEY_ENV_...` operation;
- final LB admission and destructive expiry/deletion of retained old-key material.

No confirmation token may be reused after a digest, transaction ID, proof, key,
or inventory changes.
