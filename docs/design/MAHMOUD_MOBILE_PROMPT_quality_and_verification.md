# Linas AI mobile prompt — quality, verification, and stop conditions

> Part of [MAHMOUD_MOBILE_PROMPT.md](./MAHMOUD_MOBILE_PROMPT.md)

12. ChatGPT-Like Interaction Quality

Apply the PDF’s visual shell while implementing the complete required interaction quality:

* Streaming responses.
* Real Send/Stop.
* Retry.
* Copy.
* Tool activity.
* Server-authoritative card updates.
* Offline state.
* Recoverable failure state.
* Keyboard avoidance.
* Safe-area handling.
* Scroll-position persistence per conversation.
* App restart recovery.
* No layout jump when cards update.
* No stuck Applying state.
* Dynamic font scaling.
* VoiceOver and TalkBack labels.
* Visible focus.
* Status communicated by text/icon as well as color.
* Screen-reader-readable diffs and cards.
* Per-block RTL/LTR detection.
* Mixed Arabic/English handling.
* Readable URLs, usernames, prices, numbers, and Meta account names.

The drawer stays physically on the left even when its content is RTL.

⸻

13. Customer Reply AI V2 Remains Separate

The attached mobile PDF does not define or replace Customer Reply AI V2.

Preserve the separate binding backend architecture already provided:

* Retrieval Luna and Answer Luna are separate roles.
* Both use gpt-5.6-luna.
* DM context uses the rolling last three hours, not a fixed 20-message limit.
* Full AI Basics and full Style go to Answer Luna, not Retrieval Luna.
* FAQ fast path remains protected and Published-only.
* Retrieval is limited to two rounds server-side.
* Customer name initially comes from the Meta provider profile.
* Explicit customer name correction updates the local effective name.
* Explicit gender/customer type persists.
* Preferred language follows clear language changes.
* Image comments receive image context.
* Video/Reel comments use caption and bounded cached visual context.
* Published CM only.
* No Draft leakage.
* No cross-tenant leakage.
* No Owner memory leakage.
* No raw video sent to Luna.
* No live Meta mutation.

Do not reinterpret any of these backend rules based on the PDF.

⸻

14. Implementation Quality

Do not implement the PDF as static screenshots or hardcoded sample screens.

Build reusable production components for:

* App shell.
* Headers.
* Physical-left drawer.
* Composer.
* Streaming messages.
* Activity rows.
* Proposal and status cards.
* Badges.
* Channel chips.
* Search.
* Catalog rows.
* Empty states.
* Confirmation sheets.
* Error states.
* Theme tokens.
* Per-block direction.
* Accessibility behavior.

Every visible control must:

* Be connected to a real route/action.
* Have loading, success, failure, disabled, and permission states where applicable.
* Have an accessible label.
* Respect RBAC and tenant scope.
* Avoid optimistic fake success.
* Hide when unsupported rather than appearing non-functional.

Use the existing mobile framework and backend APIs. Do not rebuild the application from zero.

Preserve unrelated user changes.

⸻

15. Required Verification

Add or update tests proving:

* Authenticated launch opens Owner Chat.
* Signed-out launch opens Guest Chat.
* No mascot or bottom tabs exist.
* Drawer is physically left.
* Drawer order is correct.
* Users is entitlement-controlled.
* Archived Chats works.
* Owner history is isolated.
* Guest and Owner stores remain isolated.
* Pending Guest draft can resume safely without importing Guest history.
* Proposal card has complete data and actions.
* Apply writes only after approval.
* Publish requires separate confirmation.
* Draft and Live are visually distinct.
* Content Management detailed controls use the required component types.
* Test Connection is read-only.
* App A is the only active Meta app.
* Live Chat has no write controls.
* Unsupported Plus/Mic/security controls are hidden.
* Streaming, Stop, Retry, Copy, offline, and recovery work.
* Arabic RTL, English LTR, Arabizi, French, and mixed-direction content render correctly.
* Touch targets and accessibility labels pass.
* App restart restores the correct Owner conversation and setup field.
* No cancelled creative route/control is reachable.
* No live Meta mutation occurs.

Run:

* Existing mobile tests.
* Unit tests.
* Integration tests.
* Typecheck.
* Lint.
* Accessibility tests.
* RTL/LTR tests.
* Navigation tests.
* Regression suites.

⸻

16. Visual Evidence

Render and provide screenshots for both light and dark themes using real test fixtures, not hardcoded production data:

* Guest Chat.
* Guest limit gate.
* Owner empty/new chat.
* Streaming Owner response.
* Greeting proposal with complete actions.
* Before/after diff.
* Applying.
* Saved as Draft.
* Publish confirmation.
* Applied/Live.
* Failure.
* Conflict.
* First-run setup.
* Setup resume.
* Physical-left drawer.
* Archived Chats.
* Content Management overview.
* Services catalog.
* Branch list.
* Structured Prices.
* FAQ catalog.
* Dynamic Messages.
* Tone.
* Handoff.
* Off Days.
* Meta diagnosis.
* Healthy Meta connection.
* Unknown/unverifiable Meta state.
* Live Chat read-only.
* Settings.
* Arabic RTL.
* Mixed Arabic/English.
* Offline and retry.

Compare the implemented screenshots against the attached PDF’s visual language.

Document every deliberate deviation caused by a binding V2 requirement.

⸻

17. Stop Conditions and Final Report

Do not merge or deploy production.

Do not perform live Meta mutation.

Stop with a complete report containing:

* Baseline mobile findings.
* Exact branch and commit SHA.
* Files changed and purpose.
* Screens/routes implemented.
* Reusable components added.
* PDF conflicts corrected.
* Any unsupported controls hidden.
* Test commands and pass/fail counts.
* Light/dark screenshots.
* RTL/LTR evidence.
* Accessibility evidence.
* Owner/Guest/customer isolation proof.
* App A-only proof.
* No-live-Meta-mutation proof.
* Remaining blockers.
* Exact merge/deployment state.

Do not claim completion after styling only a few representative screens.

The result is complete only when the PDF’s visual language is applied to the full working mobile experience while every current System Copilot V2 and Customer Reply AI V2 behavioral and security requirement remains intact.
