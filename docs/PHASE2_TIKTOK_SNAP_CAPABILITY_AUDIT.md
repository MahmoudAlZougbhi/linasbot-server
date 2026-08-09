# Wave 10 — TikTok / Snapchat capability audit

**Status:** Audit only. No production connectors implemented.  
**Date:** 2026-08-09  
**Prerequisite:** Meta DM path stable; comment/publish only when Meta-approved + live_verified.

## Policy

Every connector must declare capabilities explicitly. UI shows only:

1. Integration supported by Linas AI
2. Platform API allows for our app type
3. Required permissions actually approved
4. Tenant connection has the capability

Never claim automated customer DMs unless the official API permits our use case.

## TikTok (preliminary)

| Capability | Status | Notes |
|------------|--------|-------|
| Content publish | Coming later | Requires TikTok Content Posting API / Login Kit review |
| Analytics | Coming later | Research Business API scopes |
| Comments | Coming later | Not claimed |
| Messaging / automated DMs | Unavailable | Do not fake Meta-equivalent DM automation |

## Snapchat (preliminary)

| Capability | Status | Notes |
|------------|--------|-------|
| Content publish | Coming later | Public Profile / Marketing API review required |
| Analytics | Coming later | |
| Comments | Coming later | |
| Messaging / automated DMs | Unavailable | Do not fake |

## Next implementation gate

Before coding TikTokConnector / SnapConnector:

1. Complete official developer program enrollment
2. Document approved scopes with evidence
3. Map scopes → capability matrix in `services/integration_capabilities.py`
4. Ship only verified capabilities
