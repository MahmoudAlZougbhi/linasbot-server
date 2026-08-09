/Users/alzoughbi/Library/Containers/net.whatsapp.WhatsApp/Data/tmp/documents/5D17E082-3E83-4479-B91D-C2C8517B90E3/LINAS_AI_SCREEN_BY_SCREEN_MOBILE_DESIGN_HANDOFF(2).pdf  LINAS AI — MOBILE UI IMPLEMENTATION FROM THE ATTACHED DESIGN HANDOFF

Attachment:

LINAS_AI_SCREEN_BY_SCREEN_MOBILE_DESIGN_HANDOFF(2).pdf

Scope: Linas AI only.

Do not touch BOC or SportBook.

This is an implementation task. Continue from the current Linas AI System Copilot V2 feature branch and preserve all Owner Copilot and Customer Reply AI V2 work already completed or currently in progress.

Do not restart the project, replace the backend architecture, or create a competing mobile implementation.

⸻

1. Specification Precedence

Use the attached PDF as the visual design reference for:

* Overall Linas visual language.
* Colors and theme tokens.
* Typography hierarchy.
* Spacing.
* Cards.
* Header treatment.
* Physical-left drawer.
* Chat-first layout.
* Light/dark parity.
* Representative mobile screen composition.
* Read-only Live Chat appearance.
* Content Management overview appearance.
* Settings grouping.

The PDF is not the final authority for backend behavior, model selection, security, memory, tool execution, proposals, Content Management lifecycle, or Customer Reply AI.

Precedence order:

1. The current LINAS AI — SYSTEM COPILOT V2 implementation prompt.
2. The current LINAS AI — CUSTOMER REPLY AI V2 implementation prompt.
3. Existing verified canonical backend contracts.
4. This mobile implementation prompt.
5. The attached PDF as a visual reference.

Where the PDF conflicts with the current V2 prompts, the current V2 prompts win.

Do not rely on the PDF’s reference to an unseen “83-screen registry and 530-control matrix.” Unless those exact current specifications are present, verified, and confirmed not to contain cancelled behavior, they are not authoritative.

Do not revive any older Creative Studio, Smart Messaging, booking, WhatsApp inbound AI, manual customer takeover, or duplicate setup architecture.

⸻

2. Core Visual Direction to Preserve

Implement the PDF’s approved visual direction:

* Authenticated app opens directly to the main Owner Copilot chat.
* Signed-out app may open Guest Chat.
* One physical-left drawer.
* No bottom navigation.
* No right-side drawer.
* No dashboard-first home.
* No mascot, face, robot, character, or assistant avatar.
* The Linas star may appear only as a static logo or micro-mark.
* Do not turn the star into an animated character or fake “thinking” object.
* User messages appear on the right.
* Linas messages, activity rows, and cards appear on the left.
* Fixed rounded composer.
* Send changes to Stop only during a real active stream.
* Light and dark themes have identical content, routes, behavior, and accessibility.
* Minimum 44×44 targets; preserve the PDF’s preferred 48×48 targets.
* Physical drawer remains on the left in both LTR and RTL.
* No creative post, caption, Story, Reel, image-generation, video-generation, scheduling, content-calendar, queue, or social-publishing UI.

Do not hardcode the PDF’s sample business, Sample Studio, names, counts, statuses, or timestamps.

All displayed state must come from the real authenticated APIs or clearly marked development fixtures.

⸻

3. Correct Model Rules

Ignore every PDF sentence that says:

* “Select the strongest evaluated model per task.”
* “The server model router selects the strongest evaluated model.”

The binding runtime models are:

* Owner Copilot: gpt-5.6-sol
* Guest Chat: gpt-5.6-luna
* Customer Retrieval Luna: gpt-5.6-luna
* Customer Answer Luna: gpt-5.6-luna

Do not silently downgrade any of these to gpt-4o-mini or another model.

Model names and keys remain server-side and must never be displayed in the app.

⸻

4. Guest Chat and Authentication Corrections

Keep the PDF’s ten accepted Guest prompts and hard gate before unique prompt 11.

However, Guest and Owner memories must remain securely separate.

After authentication:

* Do not merge the Guest transcript store into Owner conversation history.
* Do not attach the complete Guest memory to the tenant’s Owner memory.
* Preserve the unsent draft and pending intent for UX continuity.
* Create a new authenticated Owner conversation after workspace resolution.
* Transfer only the explicitly preserved pending draft/intent through a typed server-authorized handoff.
* Keep the original Guest transcript isolated in Guest storage.
* Never expose tenant data before authentication and authorization finish.

Guest Chat has:

* No tenant tools.
* No tenant state.
* No Content Management mutations.
* No Meta actions.
* No claim that it changed anything.

The Plus and microphone controls shown in the PDF may appear only when their complete secure end-to-end flows genuinely work.

If voice transcription, attachments, or guest-safe analysis are incomplete, hide the corresponding control. Do not show non-working controls.

Add real:

* Stop.
* Retry.
* Copy.
* Offline.
* Recoverable failure.
* Preserved draft.
* Keyboard-safe states.

⸻

5. Owner Proposal Screen Corrections

Page 4 is a visual style reference only. Its proposal card is functionally incomplete.

Do not implement a proposal card containing only:

* Review in Content Management.
* Discard.

The complete server-authoritative Change Proposal card must support the current Owner Copilot V2 contract.

Display as applicable:

* Proposal ID.
* Human-readable title.
* Status badge.
* Exact target product path.
* Exact CM section and field.
* Current value.
* Proposed value.
* Clear before/after diff.
* Reason.
* Impact.
* Affected channel chips.
* Draft versus Published/Live target.
* Validation result.
* Side effects.
* Created source revision.
* Expiry.
* Last checked timestamp.
* Conflict information.
* Real backend state.

Actions based on actual state:

* Review.
* Edit proposal.
* Approve and apply to Draft.
* Review the exact field in Content Management.
* Discard.
* Refresh proposal.
* Retry.
* Publish only when a separately confirmed publish action is valid.
* Undo only when a real audited rollback exists.

Required states include:

* Needs information.
* Draft proposal.
* Pending approval.
* Applying.
* Saved as Draft.
* Publishing.
* Applied/Live.
* Conflict.
* Failed.
* Discarded.
* Expired.
* Superseded.

Approval inside Owner Chat may save an authorized change to the canonical CM Draft.

Publishing remains a separate explicit confirmation.

Do not force every approved proposal out of Chat and into Content Management before it can be saved.

Add real backend-created activity rows such as:

* Checking the current setting.
* Reading the current greeting.
* Comparing Draft and Live.
* Preparing a proposal.
* Validating.
* Waiting for approval.
* Applying.
* Verifying.
* Failed to verify.

Never display chain-of-thought, fake progress, artificial timers, raw JSON, prompts, tokens, or stack traces.

Add Copy and Retry to Owner messages and ensure a failed operation never remains stuck on Applying.

⸻

6. Drawer Corrections

Preserve the PDF’s physical-left drawer and visual style.

Use this binding product-module order:

1. Dashboard / Status.
2. Content Management.
3. Live Chat.
4. Integrations.
5. Users, only when the tenant is entitled.
6. Subscription.
7. Usage & Credits.
8. Settings.

Do not always display Team.

Use Users and enforce entitlement server-side.

After product modules, display Owner conversation controls:

* New Chat.
* Search.
* Pinned Chats.
* Recent History.
* Archived Chats.

Archived Chats must be a real working destination, not only an Archive action hidden inside a row menu.

Each Owner history row supports:

* Open.
* Pin/unpin.
* Rename.
* Archive/unarchive.
* Guarded Delete confirmation.

Delete must name the selected conversation and require confirmation.

Owner Copilot history must never include:

* Instagram customer DMs.
* Facebook customer messages.
* Comments.
* Live Chat audit threads.
* Guest conversations.
* Another tenant’s conversations.

Preserve workspace/account, notifications when genuinely implemented, and guarded logout below the scrollable conversation area.

⸻

7. Content Management Corrections

Page 6 is only an overview reference. It does not define the complete Content Management implementation.

Use the PDF’s clean overview layout, readiness card, search, section rows, badges, counts, and guided setup entry.

Do not use Active and Activate AI Configuration as the primary user-facing lifecycle terminology.

Use a clear lifecycle:

* Draft.
* Review.
* Valid.
* Published / Live.

Use an explicit action such as:

* Review Draft.
* Validate Draft.
* Review & Publish.

Publishing Content Management configuration remains required.

The cancelled “social publishing” functionality means publishing posts, Stories, Reels, images, videos, or scheduled social content. It does not mean removing CM Draft → Publish.

Rename FAQ & Smart Answers to FAQ or FAQ & Answers.

Do not revive legacy Smart Messaging terminology or runtime.

All required canonical sections must remain reachable:

* AI Basics.
* Languages.
* Style and Tone.
* Dynamic Messages.
* Services or Products.
* Branches or Locations.
* Prices and Offers.
* Care.
* Knowledge.
* FAQ.
* Handoff.
* Restricted Topics.
* Sources.
* Allowed AI Actions.
* AI Limits.
* Off Days.
* Specific Off Days.
* Any other verified canonical active section.

Implement the simplified editors required by System Copilot V2:

* Services: searchable catalog/list, category filter, active state, price reference, Add/Edit sheet.
* Branches: searchable compact list, address, contact, hours, active state.
* Prices: structured rows linked to service and optional branch.
* FAQ: searchable Q&A catalog with Add/Edit sheet.
* Dynamic Messages: template cards, language/channel state, preview, Draft/Live.
* Languages: searchable multi-select and default language.
* Tone: preset chips, reply preview, optional notes.
* Restricted Topics: catalog/chips and optional custom entry.
* Handoff: trigger, destination, branch/channel behavior, preview.
* Off Days: weekly selector, specific-date exceptions, timezone.
* Sources: source type, processing state, and processed date.

Do not fall back to old pages containing repeated empty text boxes.

Owner Chat setup and manual Content Management must edit the same canonical Draft records.

⸻

8. First-Run Setup and Missing Owner Cards

The eight PDF screens are representative screens, not the complete product.

Implement all required System Copilot V2 screens and states that are missing from the PDF, including:

* New-owner welcome in the same Owner Chat.
* Setup progress card.
* One meaningful setup question at a time.
* Field-level persistence.
* Save and Continue Later.
* Skip for Now.
* Back.
* Choose Another Section.
* Grouped confirmation when one answer contains several facts.
* Exact resume after app restart or logout.
* Final review.
* Validation.
* Explicit publish.
* Separate readiness states for information, Draft, integration, channel, published content, and Customer AI live.

Implement server-authoritative cards for:

* Change Proposal.
* Diagnosis.
* Setup Progress / Next Step.
* Account or Usage Summary.
* Applying.
* Success / Applied.
* Failure.
* Conflict.

Follow the PDF’s white rounded-card styling and Linas green accent, while preserving the complete current backend payload and state machine.

⸻

9. Meta Integration Corrections

Preserve the PDF’s clean connected-assets and independent DM/comment capability design.

Binding corrections:

* App A is the only active Meta app.
* App B must be unreachable from active product paths.
* Never expose tokens, App Secrets, verify tokens, Client Secrets, authorization headers, or complete external asset IDs.
* Connected may render only after authoritative server verification.
* DM and comment capability states remain independent.

Test Connection must perform a read-only health refresh only.

It must not silently:

* Reconnect an account.
* Change Page subscriptions.
* Change subscribed fields.
* Change webhooks.
* Change permissions.
* Change channel toggles.
* Reconcile a connection through mutation.
* Rotate or refresh credentials through an unauthorized flow.

If a repair requires mutation, show a separate proposal or external owner step with the correct high-impact confirmation.

Disconnect may remain a guarded authorized future route, but do not execute or test it against live assets during this task.

Do not perform any live Meta mutation.

⸻

10. Live Chat

Keep Page 8’s Live Chat direction.

Live Chat is strictly read-only.

It may contain:

* Search.
* Filters.
* Channel/account identity.
* Customer transcript.
* AI reply state.
* Delivery state.
* Handoff state.
* Webhook/event information.
* Redacted errors.
* Copy visible message text.
* Report issue using an opaque safe event reference.
* Ask Linas about this conversation using an opaque safe reference.

It must display a visible and accessible Read Only or Audit Mode state.

It must never contain:

* Composer.
* Send.
* Manual reply.
* Attachment upload.
* Microphone.
* Pause AI.
* Human takeover.
* Hidden message-write shortcut.
* Disabled fake composer shell.

Owner Chat and Live Chat data must remain separate in storage, search, permissions, and history.

⸻

11. Settings Corrections

Use Page 9’s clean grouping and visual style.

Do not create a duplicate business-information store.

Settings → Business Profile must either:

* Contain only account/legal/workspace metadata that is not customer-facing AI knowledge, or
* Deep-link to the same canonical CM fields.

It must not duplicate Content Management → AI Basics.

Keep customer-AI languages separate from the app UI language.

Only display controls such as:

* Notifications.
* MFA.
* Passkeys.
* Recovery.
* Data export.
* Account deletion.

when their complete backend flows are genuinely implemented.

Do not show placeholder or dead-end security controls.

Keep logout guarded and account deletion as a separate recently authenticated destructive flow.

⸻

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