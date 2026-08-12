# Resend production secrets (Linas AI)

**Date:** 2026-08-12  
**Constraint:** Do not merge/deploy PR #240 solely for this wiring. Never commit or print secret values.

## Runtime source of truth

| Layer | Role |
|-------|------|
| `/opt/linasbot/.env` on each app node | **Runtime SoT** (`systemd` `EnvironmentFile`) |
| GitHub repo secrets `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET` | Apply-time store for `Resend Secrets Apply` workflow (node01 / `SSH_HOST`) |
| Protected GH Environment `production` | **Not used** (repo has `meta-social-cutover` only) |

Deploy (`deploy.yml`) does **not** inject Resend keys; it SSHs and leaves host `.env` intact.

## Required variables

| Name | Kind | Notes |
|------|------|-------|
| `RESEND_API_KEY` | SECRET | **SENDING_ONLY** runtime key (domain-restricted). Never Full Access. |
| `RESEND_WEBHOOK_SECRET` | SECRET | Svix `whsec_…` for `POST /api/webhooks/resend` |
| `RESEND_FROM_EMAIL` | non-secret | `no-reply@linasaibot.com` |
| `RESEND_FROM_NAME` | non-secret | `Linas AI` |
| `RESEND_REPLY_TO` | non-secret | `support@linasaibot.com` |
| `RESEND_FROM` | non-secret | Combined `Linas AI <no-reply@linasaibot.com>` (compat) |

Forbidden in runtime: `RESEND_API_KEY_FULL`, any Full Access key, keys in Git / mobile / frontend.

## Apply paths

1. **Both HA nodes (preferred for this wiring):**  
   `bash scripts/ha/apply_resend_secrets_both_nodes.sh`  
   Loads gitignored `.env.local` (`RESEND_API_KEY_SENDING` → runtime `RESEND_API_KEY`).
2. **On-host / Actions (node01):**  
   `scripts/prod_apply_resend_secrets.sh` via workflow `resend-secrets-apply.yml`.

Permissions: `.env` mode `0600`. Apply scripts never echo secret values (fingerprints/lengths only).

## Hygiene

After setup, **revoke/rotate** any temporary Full Access Resend key that was used for domain/DNS/API-key creation. Runtime must keep using SENDING_ONLY only.

## Verification checklist

- Both nodes: keys present, `RESEND_API_KEY_FULL` absent, mode `0600`, process environ fp match
- App code (after PR #240 deploy): `/api/ready` / `mail_configured`, one transactional test send, webhook signature + delivered/bounce store

## Verification record (2026-08-12)

| Field | Result |
|-------|--------|
| Runtime SoT | Host `/opt/linasbot/.env` (both nodes); GH repo secrets for apply workflow |
| GH Environment | No `production` env; secrets at **repo** level (same as OpenAI) |
| Both-node status | **configured** — api fp `3d4180d90c0b67aa`, webhook fp `73dfbad7eedb6370`, mode `0600`, Full Access absent |
| Runtime key scope | **SENDING_ONLY** (fp matches local `RESEND_API_KEY_SENDING`, not Full Access) |
| Webhook secret configured | **yes** |
| Test email | **ok** via sending-only key → `support@linasaibot.com` (HTTP 200, message id present) |
| Webhook verification | **PASS** locally (signature accept/reject + delivered/bounce idempotent store); `tests/test_resend_email_system.py` 10 passed |
| Live `/api/webhooks/resend` | Not on production build yet (PR #240 not deployed) — prod returns auth gate for missing route |
| Full Access hygiene | **Revoked** setup key `LINAS AI` (id `f35333f3-…`) via Resend API; SENDING_ONLY re-verified HTTP 200. Residual dashboard key **Onboarding** (`570f367c-…`) remains — needs another Full Access key or dashboard delete (**OWNER_ONLY**). Local `.env.local` `RESEND_API_KEY_FULL` line removed. |

PR #240 was **not** merged or deployed for this task.
