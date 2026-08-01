# Instagram and Facebook AI messaging setup

The code supports one Meta app connected to a Facebook Page and its linked Instagram professional account. The AI answers inbound text DMs. Appointment and human-agent requests are routed deterministically to the correct WhatsApp number; the social channel cannot execute CRM appointment tools and never enters the dashboard human-takeover queue.

## Meta assets and access required

1. A published Facebook Page.
2. An Instagram Business or Creator account connected to that Page.
3. A Meta Business Portfolio that owns both assets and is business-verified.
4. A Meta developer app owned by that business.
5. Admin/full-control access for the person completing setup.
6. Advanced Access/App Review for the permissions used with public customers.

Permissions normally required for the Page-linked implementation:

- Facebook Messenger: pages_messaging, pages_manage_metadata, and pages_read_engagement.
- Instagram messaging: instagram_basic, instagram_manage_messages, and pages_manage_metadata.
- If Instagram Login is used instead of Facebook Login, Meta uses the newer instagram_business_basic and instagram_business_manage_messages scopes. Do not mix the two login models.

Official references:

- https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
- https://www.postman.com/meta/messenger-platform-api/documentation/iyp204x/messenger-platform-api

## Production environment

Set the Meta secret/token variables from `.env.example` on the DigitalOcean production service. Never commit real tokens or app secrets.

### Public WhatsApp routing numbers

Tracked defaults ship in `services/social_contact_routing.py` (`DEFAULT_SOCIAL_WHATSAPP_CONTACTS`) so routing works after deploy without requiring env vars. Optional env overrides (same keys) win when set:

| Key | Default | Use |
|---|---|---|
| `SOCIAL_WHATSAPP_BEIRUT_FEMALE` | `+96178847527` | Laser — women — Beirut / Ramlet El Bayda |
| `SOCIAL_WHATSAPP_ANTELIAS_FEMALE` | `+96170707354` | Laser — women — Antelias |
| `SOCIAL_WHATSAPP_BEIRUT_MALE` | `+96171534928` | Laser — men — Beirut / Ramlet El Bayda |
| `SOCIAL_WHATSAPP_ANTELIAS_MALE` | `+96171226082` | Laser — men — Antelias |
| `SOCIAL_WHATSAPP_TATTOO_REMOVAL` | `+96171534928` | Tattoo removal — Beirut only — all genders |

Customer-facing replies always use WhatsApp only (no calls) and a canonical `https://wa.me/<digits>` link generated from the authoritative phone number. Do **not** use `wa.link` short links.

Business rules enforced in code:

1. Instagram/Facebook never create, edit, reschedule, cancel, or claim appointments.
2. Social DMs never activate dashboard human takeover.
3. General service/pricing/preparation/branch/policy questions stay with the AI.
4. Booking or human-agent intent routes to WhatsApp after collecting missing laser branch/gender (once each).
5. Tattoo removal skips gender and Antelias selection; contact is Beirut-only.

## Meta dashboard configuration

1. Add Messenger and Instagram products to the app.
2. Generate a durable Page access token with the required permissions.
3. Set the callback URL to `https://www.linasaibot.com/webhook/meta-messaging`
4. Set the same random value in Meta and `META_WEBHOOK_VERIFY_TOKEN`.
5. Subscribe the Page/app to message and postback events (at minimum `messages` and `messaging_postbacks`).
6. Install/subscribe the app to the Facebook Page and linked Instagram account.
7. Test in Development mode with app-role accounts.
8. Complete App Review/Advanced Access, switch the app Live, then test with a real non-role customer.
9. Set `META_SOCIAL_MESSAGING_ENABLED=true` only after Meta credentials are present.

Send API notes:

- Page-linked Instagram Messaging uses `POST /{PAGE_ID}/messages` with the Page access token and the customer IGSID.
- Facebook Messenger uses the same Page endpoint with the customer PSID.
- `META_INSTAGRAM_ACCOUNT_ID` is kept for webhook channel detection / Instagram Login fallback; it is not required as the send path when `META_PAGE_ID` is set.

The POST webhook is verified with `X-Hub-Signature-256` using `META_APP_SECRET`. It acknowledges valid webhooks immediately and processes the AI response in the background. Duplicate `mid` values are ignored for a short TTL.

## Platform constraints

- The customer must initiate the conversation (or use another allowed opt-in path).
- Automated replies must stay inside Meta's allowed messaging window.
- Meta's `HUMAN_AGENT` tag is for real human support, not AI automation.
- Group DMs and arbitrary unsolicited outbound DMs are not supported.
- This integration controls messaging, not passwords, account ownership, calls, or every Instagram UI feature.

## Verification

Run:

```bash
pytest -q tests/test_meta_social_messaging.py
```

If `pytest` is unavailable in the environment, the same file can be executed with:

```bash
python3 -m unittest tests.test_meta_social_messaging -v
```

(Note: the repo's root `.gitignore` ignores `tests/`; when committing this suite, use `git add -f tests/test_meta_social_messaging.py`.)

Test at least these conversations on both channels:

1. General service/price question: AI answers normally.
2. Booking request with known gender and branch: correct number and `wa.me` link.
3. Booking request with unknown gender/branch: asks one missing field at a time.
4. Human-agent request: same WhatsApp routing behavior (no dashboard takeover).
5. Tattoo removal: shared Beirut tattoo number for either gender; never Antelias.
6. Duplicate webhook delivery: only one response.
