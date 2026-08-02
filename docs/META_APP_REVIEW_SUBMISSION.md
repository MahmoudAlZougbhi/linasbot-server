# Meta App Review submission packet

App: **Linas Clinic AI Social Bot**

Business Portfolio: **linalaser** (`2185164171581229`, Verified)

Facebook Page: **Lina’s Laser Clinics** (`378696005334409`)

Instagram professional account: `17841413184256533`

This document contains reviewer-facing factual copy. It contains no credentials,
customer messages, or reviewer passwords. Screen recordings and any dedicated
reviewer-role details must remain in the private review-evidence directory, never
in this public repository.

## Use-case narrative

A customer voluntarily sends a direct message to Lina’s Laser Clinics through
Facebook Messenger or the linked Instagram professional account. Linas AI uses
the customer’s message and relevant conversation context to answer clinic
questions about services, prices, preparation, branches, and policies.

When a customer explicitly asks to book or contact a person, the bot asks only
for the routing information that is still required: branch and gender, one field
at a time. It then supplies the correct public WhatsApp number and
`https://wa.me/...` handoff link. The bot does not book, edit, confirm, or cancel
an appointment inside Facebook, Instagram, or the clinic CRM.

The integration processes direct messages only. It does not process Facebook or
Instagram comments, publish content, send outbound marketing or unsolicited
messages, provide dashboard takeover for social conversations, accept WhatsApp
as an inbound AI channel, or integrate TikTok.

## Requested permissions

- `pages_messaging`: receive and respond to customer-initiated Messenger DMs for
  the single allowlisted Lina’s Laser Clinics Page.
- `pages_manage_metadata`: connect and maintain the Page webhook subscription for
  the `messages` and `messaging_postbacks` fields only.
- `pages_show_list`: let the authorized business administrator select the single
  target Page during setup and token issuance.
- `pages_read_engagement`: read the minimum Page identity/relationship metadata
  required by Meta’s Page-connected messaging flow. It is not used to process
  comments.
- `instagram_basic`: resolve and verify the professional Instagram account linked
  to the selected Page.
- `instagram_manage_messages`: receive and respond to customer-initiated
  Instagram DMs for the linked professional account.

Do not request `business_management` unless Meta’s current setup UI or an API
error demonstrates that the selected administrator cannot connect the verified
portfolio assets without it. Do not request publishing, comments, ads,
WhatsApp, Threads, commerce, or unrelated permissions.

## Facebook reviewer steps

1. Sign in with the dedicated Meta reviewer/tester role supplied through Meta’s
   review-access mechanism. No personal owner password or 2FA is required.
2. Open Messenger for **Lina’s Laser Clinics**.
3. Send: `Hello, what laser services do you offer?`
4. Verify one relevant Linas AI reply is received and there is no duplicate.
5. Send: `I want to book an appointment with a human.`
6. Answer the branch question with `Beirut`.
7. Answer the gender question with `Women`.
8. Verify the bot provides the Women/Beirut handoff number `+96178847527` and a
   matching `https://wa.me/96178847527...` link. Verify it does not claim an
   appointment was booked.

## Instagram reviewer steps

1. Using the same dedicated reviewer/tester role, open the linked Lina’s Laser
   Clinics Instagram professional account in Instagram DMs.
2. Send: `Hi, how should I prepare before a laser session?`
3. Verify one relevant Linas AI reply is received and there is no duplicate.
4. Send: `Please connect me to someone for tattoo removal.`
5. Verify the bot routes tattoo removal to Beirut only and supplies
   `+96171534928` with the matching `https://wa.me/96171534928...` handoff link.
6. Verify it does not create an Instagram appointment or claim a CRM booking.

## Screen-recording evidence

Create two short recordings, one for Messenger and one for Instagram. Each must
show the customer message, a single canonical AI reply, the explicit human or
booking request, the one-at-a-time routing questions, and the correct WhatsApp
handoff. Keep the browser viewport limited to the test conversation.

Before upload, verify the recording contains no App Secret, access token,
webhook verify token, terminal, browser password prompt, personal customer data,
unrelated account, or notification preview. Store the source recordings under
the private task evidence directory and upload them only to Meta’s review form.

## Data handling answers

- Data received: platform-scoped sender and destination identifiers, DM text,
  message/timestamp identifiers, postback selections, and attachment metadata.
- Purpose: authenticate/deduplicate webhooks, maintain conversation continuity,
  answer the voluntarily submitted clinic question, protect the service, and
  provide a requested human/booking handoff.
- Processors: Meta for message delivery, OpenAI for response generation,
  Google Cloud/Firebase for operational conversation storage, and DigitalOcean
  for hosting.
- Storage and retention: as described in the published Privacy Policy; a valid
  authenticated deletion request removes records under the clinic’s control.
- Security: HTTPS, strict Page/Instagram allowlists, Meta HMAC-SHA256 webhook
  validation, message-ID deduplication, echo rejection, query-secret-free access
  logging, secret storage outside the repository, and least-privilege access.
- Sale/advertising: social-message data is not sold or used for third-party ads.
- Deletion: Meta’s signed deletion callback is authenticated with the current
  App Secret; invalid, stale, malformed, or wrong-secret requests are rejected.

## Public URLs

- Website: `https://www.linasaibot.com/`
- Privacy Policy: `https://www.linasaibot.com/privacy-policy`
- Terms: `https://www.linasaibot.com/terms`
- User Data Deletion instructions and callback:
  `https://www.linasaibot.com/data-deletion`
- App domain: `linasaibot.com`

## Submission checklist

- App remains in Development mode.
- Verified portfolio association and exact Page/Instagram IDs are visible.
- Requested permissions match the list above and no unrelated permission is
  included.
- Webhook subscriptions are exactly `messages,messaging_postbacks` unless Meta
  documents a mandatory additional field already handled by the backend.
- Both controlled recordings pass the privacy check and are uploaded privately.
- Reviewer-role access works without the owner’s password or 2FA.
- Privacy, terms, and deletion URLs return public HTTPS `200`.
- The factual fields and data-handling questionnaire are complete.
- Mahmoud personally reviews and accepts any binding declaration before final
  submission.
