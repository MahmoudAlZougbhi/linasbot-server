# Linas AI mobile prompt — Guest Chat and authentication

> Part of [MAHMOUD_MOBILE_PROMPT.md](./MAHMOUD_MOBILE_PROMPT.md)

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
