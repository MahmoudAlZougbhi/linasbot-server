# Meta verified-app cutover and rollback runbook

Scope: replace the active Meta app for Facebook Page `378696005334409` and its
linked Instagram professional account `17841413184256533` without changing the
canonical Linas AI pipeline or the WhatsApp handoff matrix. The old app
`1784792718776344` remains intact as the rollback path.

## Immutable boundaries

- New app name: `Linas Clinic AI Social Bot`.
- New app must be owned from creation by verified Business Portfolio
  `linalaser` (`2185164171581229`).
- Inbound AI is limited to Facebook Messenger and Instagram DMs.
- Do not subscribe comment, feed, mention, publishing, WhatsApp, Threads, ads,
  commerce, or unrelated webhook fields/products.
- Page webhook fields are exactly `messages,messaging_postbacks` unless Meta
  documents and requires an additional field that the backend already handles.
- Do not delete, move, revoke, or edit the old app. Only its Page subscription
  may be removed immediately before the atomic credential cutover.
- Never run old and new Page messaging subscriptions at the same time.

## Readiness evidence required before cutover

1. Meta dashboard shows the new app under Business ID `2185164171581229`.
2. Verified asset access is limited to Page `378696005334409` and Instagram
   account `17841413184256533`.
3. New Page token debugging confirms the new App ID, target Page, linked
   Instagram account, required granular targets, and required permissions.
4. The public callback GET succeeds with the canonical verify token; an
   incorrect verify token returns `403`.
5. Local tests and hosted Quality Gates are green for the release SHA.
6. Privacy, terms, and deletion pages return public HTTPS `200` responses.
7. Production has a strong `DASHBOARD_AUTH_SECRET`, `ENVIRONMENT=production`,
   the existing admin user, Firebase, OpenAI, and MontyMobile readiness.
8. A root-owned, mode-600, encrypted snapshot of the old Meta environment has
   been created and its non-secret archive reference recorded. The encryption
   key exists only in the canonical GitHub Actions secret store.
9. The previous production SHA and the new release SHA are recorded.

## Atomic cutover sequence

1. Keep `META_SOCIAL_MESSAGING_ENABLED=false` in the staged new production
   secret set.
2. Revalidate the new Page token and Page-to-Instagram relationship immediately
   before cutover without printing credentials or Graph response tokens.
3. Confirm the old app is the only subscribed app for the target Page.
4. Unsubscribe the old app from the target Page. Do not alter the old app
   object, credentials, portfolio, products, or review state.
5. Atomically replace `META_APP_ID`, `META_APP_SECRET`,
   `META_PAGE_ACCESS_TOKEN`, and the fixed non-secret Meta identifiers/version
   in both active production environment files. Set
   `META_SOCIAL_NEW_APP_REQUIRED=true`, clear rollback mode, and keep messaging
   disabled. This marker makes the retired App ID fail readiness after cutover
   unless the explicit encrypted-rollback workflow is running.
6. Restart `linasbot`; require service active, Nginx valid, health ready, the
   correct verify-token challenge, wrong-token `403`, missing/invalid signature
   `401`, and WhatsApp inbound-disabled evidence.
7. Subscribe the new app to Page `378696005334409` with only
   `messages,messaging_postbacks`, then set
   `META_SOCIAL_MESSAGING_ENABLED=true` and restart once more.
8. Send controlled role/tester DMs on Facebook and Instagram. Require exactly
   one canonical AI reply per message and correct branch/gender WhatsApp
   handoff behavior.
9. Keep the app in Development mode through App Review approval. Do not claim
   non-role customer availability before Advanced Access/approval.

## Immediate rollback sequence

Trigger rollback if any credential validation, restart, health/readiness,
signature, subscription, send, deduplication, identity, canonical-AI, or handoff
check fails.

1. Disable social messaging and unsubscribe the new app from the target Page.
2. Decrypt the recorded old-app archive only inside a mode-700 temporary
   directory on production. Do not print or export its contents.
3. Restore the old Meta environment atomically to the original environment
   paths, restart `linasbot`, and verify the old App ID by equality check only.
4. Resubscribe the old app to Page `378696005334409` with
   `messages,messaging_postbacks` using the restored old Page token.
5. Re-run health/readiness, challenge, invalid-signature, WhatsApp-disabled,
   and one controlled Messenger/Instagram test per available role account.
6. Preserve the failed new app and evidence for diagnosis; do not delete either
   app and do not retry cutover until the failure is understood.
7. If code rather than credentials caused the failure, redeploy the recorded
   previous production SHA through the canonical deployment process. Never use
   an unrecorded or unreviewed working-tree state.

## Redacted evidence record

Record only IDs, timestamps, SHAs, workflow/run IDs, HTTP status codes, boolean
validation results, subscription fields, and encrypted archive references.
Never record secrets, token fragments, message content from real customers, or
screenshots containing unrelated assets or personal data.
