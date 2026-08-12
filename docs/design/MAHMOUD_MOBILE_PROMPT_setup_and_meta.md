# Linas AI mobile prompt — first-run setup and Meta integrations

> Part of [MAHMOUD_MOBILE_PROMPT.md](./MAHMOUD_MOBILE_PROMPT.md)

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
