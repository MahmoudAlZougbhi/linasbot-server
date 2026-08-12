# Linas AI Phase 2 — Wave 0 Status

**Branch:** `feat/linas-ai-phase2-app-first`  
**Date:** 2026-08-09  
**Pre-flight production SHA (origin/main at branch start):** see git merge-base with main.

## Completed in Wave 0

1. **AI Limits SoT** — Settings `POST /api/settings/ai-limits` removed (410). GET reads published CM via `services/ai_limits_source.py`. Publish sync remains the only writer into the enforcement cache. Orphan `AiLimitsPanel.jsx` removed.
2. **`platform_owner` role** — Added to RBAC; assignable only via offline CLI (`--role platform_owner` → `created_by=cli-provision-platform-owner`). Public register and tenant user APIs cannot grant it.
3. **Plan economics simulation** — `services/plan_economics.py` + `scripts/plan_economics_simulation.py`. Plan prices fixed at $24.99 / $59 / $109 / $250. Allowances recommended from configured provider rates + margin floor.
4. **Cutover documentation** — See below. No production env flags flipped in this wave.

## Production CM cutover (read-only status)

Operators must verify on the production host (not flipped by this PR):

| Check | How |
|-------|-----|
| Published pointer for `linas` | `tenants/linas/cm/published/pointer.json` under `LINASBOT_DATA_ROOT` |
| Legacy bridge | `CM_DISABLE_LINAS_LEGACY_BRIDGE` in systemd `.env` |
| Runtime mode | Existing CM cutover runbooks under `docs/cm_phase_evidence/` + `scripts/prod_cm_*` |

Wave 0 does **not** change production cutover flags (server/infra approval required).

## Infra approval request (Mahmoud rule #4)

The following are **blocked** until explicit approval:

- Redis (or equivalent) durable job queues
- Separate worker systemd units
- Production env secrets for Apple/Google IAP webhooks
- Nginx changes for mobile deep-link / store webhook paths
- Any destructive CM production migration

**Ask:** I need to change server/infra/build config for durable workers (Redis + worker processes) and later store webhook secrets. Do you approve?

Until approved, Waves 4–8 implement queue interfaces with in-process adapters for local/CI only, and must not claim production scale-ready.

## Remaining external blockers

- Meta comment scopes / `live_verified` (do not show as Available until approved)
- SMTP for email verification in all environments
- App Store / Play Console apps and products not yet created
- Redis/workers pending approval above
