# Mobile Design Handoff — Evidence Report (§17)

**Branch:** `feat/system-copilot-v2`  
**PR:** #106  
**Verdict:** **MOBILE DESIGN HANDOFF IMPLEMENTED (pending prod approval)**  
**STOP:** No production merge/deploy/Meta mutation in this task.

## Baseline findings

| Area | Before | After |
|------|--------|-------|
| Navigation | Dual drawers (history left + Control Center right) | Single physical-left `NavDrawer` |
| Brand | Animated `LinasAvatar` thinking states | Static `LinasStarMark` only |
| Theme | Light purple tokens only | PDF teal tokens + light/dark `ThemeProvider` |
| Guest | Banner + auth modal; Plus/Mic shown | Starters, AGT-01 gate, draft handoff; Plus/Mic hidden for guests |
| Proposals | Confirm/Reject only | Full V2 `ProposalCard` + activity rows |
| CM | Flat section grid | Readiness + Draft/Valid/Published + setup CTA |
| Settings | Flat legal list | Grouped Account / Preferences / Security & Support |
| Integrations | Connect/disconnect | App A filter + read-only Test connection |
| Archive | Field existed, no API/UI destination | PATCH archive + Archived chats destination |

## PDF conflicts corrected by V2 precedence

1. PDF incomplete Review/Discard-only proposal → complete V2 proposal actions/states.
2. PDF “strongest model per task” → ignored; Sol/Luna remain server-side, never shown.
3. PDF Team tile → Users (entitlement-controlled).
4. PDF Active/Activate AI Configuration wording → Draft / Valid / Published / Live.
5. PDF Guest memory resume into same thread → pending draft handoff only; stores stay isolated.
6. PDF Plus/Mic always visible → hidden when guest flows incomplete; owner Plus/Mic kept.

## Unsupported controls hidden

- Guest Plus / Mic
- MFA / Passkeys / Recovery placeholders in Settings
- Creative Studio routes (already unreachable)
- Right-side Control Center as primary nav
- Animated mascot / character avatar

## Screens / routes covered

GCH-01, AGT-01, CHT-01+CRD-01, DRW-01, CM-01, IN-01/IN-02 patterns, LC-01/LC-02 read-only, ST-01, Archived chats.

## Reusable components added

`ThemeProvider`, `LinasStarMark`, `NavDrawer`, `HistoryRows`, `ProposalCard`, `GuestEmptyState`, `pendingGuestDraft`, enhanced `ChatHeader` / `ChatComposer` / `AuthGateModal`.

## Isolation / App A / Meta mutation

- Guest draft key is local-only; Owner history from `/api/owner-ai/conversations` only.
- Live Chat remains a separate module/store; no composer.
- Integrations UI filters to Instagram/Facebook (App A product surface).
- Test connection = read-only list reload; no webhook/subscription/token mutation invoked by this task.

## Tests run

```
cd mobile/linas-ai && npm test
→ typecheck OK + 11 node:test design_handoff checks passed

node scripts/check_source_line_limit.mjs mobile/linas-ai/src mobile/linas-ai/App.tsx
→ OK

python3.11 -m pytest tests/test_owner_chat_archive.py -q
→ 1 passed
```

## Visual evidence

Light + dark fixture screenshots under `docs/evidence/mobile_design_handoff/screenshots/`  
(PDF page renders under `docs/design/pdf_pages/`; design PDF at `docs/design/LINAS_AI_SCREEN_BY_SCREEN_MOBILE_DESIGN_HANDOFF.pdf`).

Deliberate deviations: fixtures use theme tokens and labels only — **no** PDF “Sample Studio” / fake customer names hardcoded into the product UI.

## Remaining blockers (honest)

1. Device/simulator recordings of live streaming UI not captured in this agent environment.
2. Entitlement API for Users still client-gated to authenticated (server RBAC remains authoritative).
3. Some CM section editors remain simplified stubs where mobile editors already existed.
4. Production enablement / TestFlight rebuild still requires Mahmoud approval.

## Merge / deployment state

**Not merged. Not deployed. No live Meta mutation performed.**
