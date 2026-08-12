# Linas AI mobile prompt — Live Chat

> Part of [MAHMOUD_MOBILE_PROMPT.md](./MAHMOUD_MOBILE_PROMPT.md)

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
