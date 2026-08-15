# Deployment-time admin / session migration checklist (redacted)

Do not paste secret values into tickets, chat, or commits.

## Pre-deploy

- [ ] Generate a long random **`DASHBOARD_AUTH_SECRET`** (stable across restarts; never regenerate per process).
- [ ] Confirm production **`ENVIRONMENT=production`** (or `ENV=production`).
- [ ] Confirm **`MONTYMOBILE_API_KEY`** is set when using MontyMobile (value not logged).
- [ ] Confirm Meta webhook verify token / app secret are configured out-of-band (names only here).
- [ ] WhatsApp inbound AI remains **disabled** (product contract).

## First admin (empty installation)

There is **no public HTTP bootstrap**. Provision offline on the server:

```bash
# Preferred: interactive hidden prompt
python scripts/provision_dashboard_admin.py --email owner@example.com --prompt-password

# Or password via env (not argv / not tracked files)
PROVISION_ADMIN_PASSWORD='…' python scripts/provision_dashboard_admin.py --email owner@example.com --json
```

Rules enforced by the CLI:

- Unavailable over public HTTP (`POST /api/auth/bootstrap-admin` removed).
- Refuses known/default passwords.
- Refuses to create when any user already exists (idempotent “already_provisioned”).
- Does not print the password; audit JSON has email/status only.

## Existing dashboard users

- [ ] Existing bcrypt hashes continue to work (login).
- [ ] After password change, `passwordEpoch` invalidates prior sessions; user gets a fresh session cookie.
- [ ] Role changes take effect on next authenticated request / session validation.

## Sessions / CSRF / WebView

- [ ] `DASHBOARD_COOKIE_SECURE` / `DASHBOARD_COOKIE_SAMESITE` appropriate for WebView (`none` requires Secure).
- [ ] Logout requires session + CSRF header (not a public unauthenticated endpoint).
- [ ] Login remains the only public auth mutation.

## Post-deploy checks

- [ ] `GET /api/health` → liveness ok.
- [ ] `GET /api/ready` → `ok: true` with boolean checks only (no secret values).
- [ ] Login / logout / expired session / wrong role verified in staging.
- [ ] Quality Gates workflow succeeded for the deployed SHA (deploy is gated on that success).

## Safe rollback

- [ ] Keep previous container image tag / git SHA.
- [ ] Roll back application code first; do not rotate `DASHBOARD_AUTH_SECRET` during an emergency rollback unless sessions must be globally invalidated.
- [ ] If secret must rotate: expect all sessions invalidated; re-login required.

## Emergency deploy bypass

Disabled. Product code exposes no single-node release bypass. Follow
`docs/release/TWO_NODE_RELEASE_POLICY.md`: restore green Quality Gates and use
the protected two-node recovery/release transaction. Live break-glass access is
separate, time-limited, audited, and must keep a repaired node drained until
exact pair parity is re-established.
