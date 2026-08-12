# Linas AI mobile prompt — Owner Proposal screen

> Part of [MAHMOUD_MOBILE_PROMPT.md](./MAHMOUD_MOBILE_PROMPT.md)

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
