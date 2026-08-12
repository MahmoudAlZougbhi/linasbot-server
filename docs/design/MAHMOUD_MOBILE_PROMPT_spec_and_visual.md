# Linas AI mobile prompt — specification, visual direction, models

> Part of [MAHMOUD_MOBILE_PROMPT.md](./MAHMOUD_MOBILE_PROMPT.md)

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
