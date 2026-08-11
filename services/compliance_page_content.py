"""HTML bodies for public Privacy, Terms, and Data Deletion pages.

Kept separate from FastAPI route handlers so compliance copy can grow without
pushing ``modules/meta_compliance.py`` over the project file-size guideline.
Copy must stay accurate to shipped product behavior (no invented addresses,
jurisdictions, or live channel claims).
"""

from __future__ import annotations

import html


def privacy_policy_body(*, contact_email: str, public_base_url: str) -> str:
    email = html.escape(contact_email)
    base = html.escape(public_base_url.rstrip("/"))
    return f"""
<h1>Privacy Policy</h1>
<p class="meta">Effective 11 August 2026 · Last updated 11 August 2026</p>

<p>This Privacy Policy describes how <strong>Linas AI</strong> (“we”, “us”, or “Operator”)
collects, uses, stores, shares, and deletes personal data when you use our website,
mobile app, operator dashboard, Owner chat, AI Setup (Content Manager), social-channel
automations, guest marketing chat, and related membership services
(collectively, the “Service”).</p>

<p>Contact for privacy questions and requests:
<a href="mailto:{email}">{email}</a>.
A phone number and postal address are not published in current public materials; use
this email for all privacy and deletion requests. Canonical policy URL:
<a href="{base}/privacy-policy">{base}/privacy-policy</a>.</p>

<h2>1. Roles and relationships</h2>
<ul>
  <li><strong>Operator (Linas AI)</strong> — provides the multi-tenant SaaS platform,
  hosting, authentication, billing surfaces, and AI tooling.</li>
  <li><strong>Tenant (business customer)</strong> — the company that creates a Linas AI
  account, configures approved knowledge in AI Setup, connects social channels it
  owns or is authorized to manage, and may invite staff users.</li>
  <li><strong>End customer</strong> — a person who voluntarily messages or comments on
  a Tenant’s connected Facebook, Instagram, WhatsApp, TikTok, or other channel
  account, or who uses public guest chat on our marketing site.</li>
</ul>
<p>For end-customer social messages processed on a Tenant’s connected assets, the
Tenant typically decides the business purpose of the conversation and supplies the
approved knowledge used in replies. Linas AI processes that messaging data to
operate the Service for that Tenant. Staff should treat Tenant knowledge and
end-customer messages as confidential to that Tenant.</p>

<h2>2. Channels we may process</h2>
<p>When a Tenant connects accounts through official platform integrations, Linas AI
may process customer direct messages and, where the Tenant enables it, public
comments on:</p>
<ul>
  <li><strong>Facebook</strong> — Messenger and Page comments (primary live Meta
  connection today).</li>
  <li><strong>Instagram</strong> — professional-account DMs and comments (primary live
  Meta connection today).</li>
  <li><strong>WhatsApp</strong> — (a) outbound human-contact / booking handoff links
  (for example a public <code>https://wa.me/...</code> destination configured by the
  Tenant), and (b) inbound WhatsApp Business messaging <em>only when</em> that Tenant
  connects WhatsApp through an official Meta WhatsApp / Cloud API integration that
  we have enabled for the Service. Official Cloud API coexistence is not claimed as
  universally live for every Tenant until that Tenant’s connection is actually
  available and authorized.</li>
  <li><strong>TikTok</strong> — only when connected through official TikTok APIs as
  that integration becomes available. In the current product UI, TikTok may appear
  as coming soon / not yet connectable.</li>
</ul>
<p>We do not process messaging data for accounts the Tenant has not authorized. Other
surfaces listed as coming soon (for example Snapchat) are not active data-processing
channels until connectable.</p>

<h2>3. Data we collect</h2>
<h3>3.1 Account and Tenant data</h3>
<p>When you register or sign in (mobile app or dashboard), we may collect email
address, name or display name, authentication credentials or tokens, role/permission
assignments, Tenant identifiers, and security events (for example login failures).</p>

<h3>3.2 Tenant knowledge and configuration</h3>
<p>AI Setup / Content Manager content that a Tenant enters or imports — services,
prices, FAQs, policies, handoff destinations, languages, tone, restricted topics,
and related configuration used to answer Owner chat and customer questions.</p>

<h3>3.3 Channel connection data</h3>
<p>OAuth or platform authorization records, Page / professional account / WhatsApp
business identifiers, granted scopes, webhook subscription state, encrypted access
tokens, and connection health metadata needed to send and receive messages on the
Tenant’s behalf.</p>

<h3>3.4 Messaging and comment data</h3>
<p>For connected Meta Facebook/Instagram assets, Meta may send a platform-scoped
sender identifier, destination Page or Instagram account identifier, message text,
message and timestamp identifiers, postback selections, and attachment notifications
or metadata. When a Tenant connects WhatsApp or TikTok through official APIs, the
relevant platform may send similar identifiers, destination account details, message
or comment text, and delivery metadata. The current social messaging path does not
fetch attachment files by default; it asks the sender to describe what help they
need in text when a file cannot be used.</p>
<p>Owner chat and guest marketing-chat prompts and replies may also be stored as
operational conversation records for the applicable session or Tenant.</p>

<h3>3.5 Billing and membership data</h3>
<p>Plan selection, entitlement state, usage/credit ledger entries, and purchase
receipts or checkout references when Apple In-App Purchase, Google Play Billing,
and/or Stripe (when configured) are used. Payment card numbers are processed by
those payment providers — not stored as full PAN data in Linas AI application
storage.</p>

<h3>3.6 Technical and security data</h3>
<p>IP address (for rate limiting and abuse prevention), approximate request
metadata, device/app version signals where the client sends them, operational logs
(status codes, errors, pseudonymous identifiers), and similar security telemetry.
We do not sell this data for third-party advertising.</p>

<h2>4. How we use data</h2>
<p>We use personal data to:</p>
<ul>
  <li>authenticate users, enforce roles, and protect accounts;</li>
  <li>authenticate and deduplicate inbound channel events;</li>
  <li>bind messages to the Tenant and assets that authorized the connection;</li>
  <li>preserve Tenant-isolated conversation context;</li>
  <li>answer Owner chat and customer questions from approved Tenant knowledge;</li>
  <li>run optional AI comment replies when a Tenant explicitly enables them;</li>
  <li>publish social posts only after an authorized user reviews and confirms;</li>
  <li>provide booking or human-support handoff using destinations the Tenant
  configured;</li>
  <li>operate membership, entitlements, usage metering, and customer support;</li>
  <li>secure the Service, prevent abuse, and meet legal or platform obligations.</li>
</ul>
<p>We do not publish posts automatically, run ads on your behalf from social-message
content, send unsolicited marketing DMs, hide or delete comments as a product
feature, or create appointments inside Facebook, Instagram, WhatsApp, or TikTok
solely through an automated reply.</p>

<h2>5. Service providers and third parties</h2>
<p>We share data with processors only as needed to run the Service:</p>
<ul>
  <li><strong>Meta</strong> — Facebook, Instagram, and WhatsApp platform delivery,
  OAuth, and webhooks when those integrations are used.</li>
  <li><strong>TikTok</strong> — when a Tenant connects TikTok through official APIs.</li>
  <li><strong>OpenAI (or successor LLM providers we configure)</strong> — processes
  message text and relevant conversation/context snippets to generate answers.</li>
  <li><strong>Google Cloud / Firebase</strong> — operational storage for conversation
  and related records.</li>
  <li><strong>DigitalOcean</strong> — application hosting.</li>
  <li><strong>Apple / Google</strong> — In-App Purchase / Play Billing validation when
  store subscriptions are used.</li>
  <li><strong>Stripe</strong> — card checkout for token or billing products when
  Stripe is configured for the deployment.</li>
</ul>
<p>These providers process data under their applicable contracts, security controls,
and privacy terms. We do not sell social-message data or use it for third-party
advertising.</p>

<h2>6. Storage, retention, and security</h2>
<p>Conversation records can include Tenant and asset bindings, platform-scoped
identifiers, message text, AI replies, timestamps, language, and routing state.
OAuth credentials and Page or channel tokens are encrypted server-side and are
never entered or displayed to normal dashboard users. Operational logs may contain
pseudonymous identifiers, status codes, and errors.</p>
<p>The Service does not currently apply a single fixed automatic deletion date to
all conversation records. Records remain while needed for continuity, security,
troubleshooting, billing integrity, and the Tenant’s legitimate service records,
unless a valid deletion request is completed or the records are no longer needed.
Authenticated Meta user-data deletion callbacks are processed when received; we
aim to complete deletions under our control without undue delay and to provide a
confirmation status URL for Meta-originated requests.</p>
<p>Security controls include HTTPS in transit, access restrictions, Meta webhook
HMAC signature validation where applicable, and keeping production credentials
outside the source repository.</p>

<h2>7. International transfers</h2>
<p>The Service is hosted and may store or process data in facilities used by our
providers (including cloud regions selected for DigitalOcean, Google Cloud/Firebase,
and LLM providers). If you access the Service from another country, your data may
be transferred to and processed in those locations. We rely on appropriate
contractual and security measures with providers.</p>

<h2>8. Your choices and rights</h2>
<p>Depending on applicable law, you may request access, correction, deletion,
restriction, or information about processing. End customers can stop messaging a
business at any time. Deletion instructions for social-message data, Meta
callbacks, and Tenant account requests are published at
<a href="/data-deletion">Data Deletion</a>. We may ask for enough information to
verify the relevant Facebook, Instagram, WhatsApp, TikTok, or account record before
acting.</p>

<h2>9. Children’s privacy</h2>
<p>Linas AI is a business productivity and customer-support Service. It is not
directed to children under 13 (or under the digital age of consent in the relevant
jurisdiction). We do not knowingly collect personal data from children for the
purpose of offering the Service to them. If you believe a child has provided
personal data inappropriately, contact us and we will take reasonable steps to
delete it.</p>

<h2>10. WhatsApp and human handoff</h2>
<p>Until a Tenant connects inbound WhatsApp AI through an official WhatsApp Business
/ Cloud API integration that we enable, WhatsApp is primarily an outbound booking
or human-agent destination. When a sender explicitly asks to book or reach a
person, Linas AI may ask for the minimum routing information needed to provide the
correct public contact link configured by that Tenant. No appointment is created
inside Facebook, Instagram, WhatsApp, TikTok, or a business CRM solely by the
automated reply.</p>

<h2>11. Changes</h2>
<p>We may update this Privacy Policy when the Service or legal requirements change.
The effective date above will be revised when material updates are published at
<a href="{base}/privacy-policy">{base}/privacy-policy</a>. Continued use of the
Service after an update constitutes notice of the revised policy for Tenant users
subject to applicable law.</p>

<h2>12. Contact</h2>
<p>Questions about this policy:
<a href="mailto:{email}">{email}</a>.</p>
"""


def terms_of_service_body(*, contact_email: str, public_base_url: str) -> str:
    email = html.escape(contact_email)
    base = html.escape(public_base_url.rstrip("/"))
    return f"""
<h1>Terms of Service</h1>
<p class="meta">Effective 11 August 2026 · Last updated 11 August 2026</p>

<p>These Terms of Service (“Terms”) govern access to and use of <strong>Linas AI</strong>
(the “Service”), including our website at <a href="{base}">{base}</a>, mobile
application, operator dashboard, Owner chat, AI Setup (Content Manager), social
channel automations, guest marketing chat, and membership features. By creating an
account, connecting a channel, or using the Service, you agree to these Terms and
our <a href="/privacy-policy">Privacy Policy</a>.</p>

<p>Contact: <a href="mailto:{email}">{email}</a>.</p>

<h2>1. Who the Service is for</h2>
<p>Linas AI is a business customer-support and Tenant-knowledge AI. Each business
(“Tenant”) configures approved facts, policies, and reply behavior in AI Setup.
Owner chat helps the business owner operate the Tenant. Customer-facing replies
apply only on channels the Tenant has authorized through official platform
integrations when those connections are available.</p>

<h2>2. Accounts and eligibility</h2>
<p>You must provide accurate registration information and keep credentials
confidential. Tenant owners are responsible for staff users they invite and for
actions taken under their Tenant. You may use the Service only if you can form a
binding contract and only for lawful business purposes.</p>

<h2>3. Channels and platform rules</h2>
<p>Supported or planned channel surfaces include Facebook, Instagram, WhatsApp, and
TikTok. Facebook and Instagram are the primary live Meta connections today.
WhatsApp may be used for outbound handoff links and, when officially connected,
inbound Business messaging. TikTok appears when official API connectivity is
offered (and may show as coming soon until then). You must:</p>
<ul>
  <li>connect only business accounts you own or are authorized to manage;</li>
  <li>comply with Meta, WhatsApp, TikTok, Apple, Google, and other platform
  policies that apply to your use;</li>
  <li>not attempt to bypass platform messaging windows, consent rules, or
  security controls.</li>
</ul>

<h2>4. Tenant responsibilities for knowledge and replies</h2>
<p>You are responsible for the accuracy, legality, and appropriateness of knowledge
you approve in AI Setup and for review/activation workflows. Automated replies are
generated from that knowledge and may be incomplete. Confirm important treatment,
eligibility, pricing, medical, legal, or financial details with qualified staff
when those topics apply. Linas AI does not provide medical diagnosis, emergency
care, or professional advice.</p>

<h2>5. Appointments and human contact</h2>
<p>Linas AI does not create, edit, reschedule, cancel, or confirm appointments
inside Facebook, Instagram, WhatsApp, TikTok, or a business CRM solely through an
automated social reply. When a sender explicitly requests booking or a person, the
Service may provide the public contact channel you configured after collecting only
required routing information. An appointment exists only after your staff confirm
it through your applicable booking process.</p>

<h2>6. Publishing and comments</h2>
<p>Optional AI comment replies are off by default and run only when enabled per
connected asset. Social posts created through the Service publish only after an
authorized user reviews the caption/preview and confirms publishing. Do not use
the Service to send spam, unlawful content, or deceptive automated engagement.</p>

<h2>7. Membership, usage, and payments</h2>
<p>Paid plans, credits/tokens, and store subscriptions may be offered through Apple
In-App Purchase, Google Play Billing, and/or Stripe checkout when those surfaces
are configured. Prices and entitlements are as shown in the applicable store or
billing UI at purchase time. Platform store terms also apply to store purchases.
Refunds follow the rules of the store or payment provider that processed the
charge, except where mandatory law requires otherwise.</p>

<h2>8. Acceptable use</h2>
<p>You may not: misuse the Service; attack or probe infrastructure; scrape beyond
ordinary use; reverse engineer except where mandatory law allows; upload malware;
infringe others’ rights; process data unlawfully; or use the Service to harm
minors. We may suspend or terminate access for abuse, non-payment, legal risk, or
platform policy violations.</p>

<h2>9. Intellectual property</h2>
<p>Linas AI and its software, branding, and documentation remain our property (or
our licensors’). Tenant knowledge and content you upload remain yours. You grant
us a limited license to host and process that content solely to provide the
Service to your Tenant. End-customer messages remain subject to the applicable
platform’s terms and privacy rules.</p>

<h2>10. Third-party services</h2>
<p>The Service depends on third parties (including Meta, TikTok when enabled,
OpenAI or other LLM providers, cloud hosts, and payment platforms). Their outages,
policy changes, or API limits may affect availability. We are not responsible for
third-party platforms you connect.</p>

<h2>11. Disclaimers</h2>
<p>THE SERVICE IS PROVIDED “AS IS” AND “AS AVAILABLE” TO THE MAXIMUM EXTENT
PERMITTED BY LAW. WE DISCLAIM WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE, AND NON-INFRINGEMENT. AI OUTPUTS MAY BE INCORRECT OR
OUTDATED; YOU MUST SUPERVISE BUSINESS-CRITICAL USE.</p>

<h2>12. Limitation of liability</h2>
<p>TO THE MAXIMUM EXTENT PERMITTED BY LAW, LINAS AI AND ITS OPERATORS WILL NOT BE
LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR LOST-PROFIT DAMAGES,
OR FOR LOSS OF DATA, GOODWILL, OR BUSINESS INTERRUPTION. OUR AGGREGATE LIABILITY
FOR CLAIMS RELATING TO THE SERVICE IN ANY TWELVE-MONTH PERIOD WILL NOT EXCEED THE
AMOUNTS YOU PAID TO US FOR THE SERVICE IN THAT PERIOD (OR, IF GREATER, USD $100
WHERE NO FEES WERE PAID). SOME JURISDICTIONS DO NOT ALLOW CERTAIN LIMITATIONS;
IN THOSE CASES OUR LIABILITY IS LIMITED TO THE FULLEST EXTENT PERMITTED.</p>

<h2>13. Termination and data</h2>
<p>You may stop using the Service at any time. To request deletion of Tenant
account data or end-customer social-message records under our control, follow
<a href="/data-deletion">Data Deletion</a>. We may retain limited records as
required for security, fraud prevention, accounting, or legal compliance.</p>

<h2>14. Changes</h2>
<p>We may update these Terms when the Service or legal requirements change. The
effective date above will be revised when material updates are published at
<a href="{base}/terms">{base}/terms</a>.</p>

<h2>15. Contact</h2>
<p>Questions about these Terms:
<a href="mailto:{email}">{email}</a>.</p>
"""


def data_deletion_body(*, contact_email: str, public_base_url: str) -> str:
    email = html.escape(contact_email)
    base = html.escape(public_base_url.rstrip("/"))
    return f"""
<h1>User Data Deletion</h1>
<p class="meta">Effective 11 August 2026 · Last updated 11 August 2026</p>

<p>This page explains how to request deletion of personal data processed by
<strong>Linas AI</strong>. Canonical URL:
<a href="{base}/data-deletion">{base}/data-deletion</a>.
Privacy details:
<a href="/privacy-policy">Privacy Policy</a>.</p>

<h2>1. Whose data?</h2>
<ul>
  <li><strong>End customers</strong> — people who messaged or commented on a
  Tenant’s connected Facebook, Instagram, WhatsApp, TikTok, or similar channel.</li>
  <li><strong>Tenant users</strong> — business owners and staff with Linas AI
  accounts (email login, roles, Owner chat history tied to the account, billing
  identifiers under our control).</li>
</ul>

<h2>2. End-customer social message deletion via Meta</h2>
<p>For Facebook / Instagram interactions processed through our Meta app
integration, remove the app or request deletion through the applicable Facebook
or Instagram settings. Meta sends our server an authenticated, signed deletion
request. Valid requests remove the namespaced Facebook/Instagram user record, its
stored conversations, and matching social chat index entries under our control.
Invalid signatures are rejected.</p>
<p>After Meta accepts the request, use the confirmation code returned by Meta to
check status at
<code>{base}/data-deletion/status/&lt;confirmation-code&gt;</code>.</p>

<h2>3. End-customer deletion by email (all channels)</h2>
<p>Email
<a href="mailto:{email}?subject=Social%20message%20data%20deletion">{email}</a>
with the subject “Social message data deletion”. Include:</p>
<ul>
  <li>which channel the request concerns (Facebook Messenger, Instagram, WhatsApp,
  TikTok, or other);</li>
  <li>the public account handle, Page name, or business WhatsApp number the person
  contacted;</li>
  <li>approximate date/time of the conversation if known.</li>
</ul>
<p>Do <strong>not</strong> send a password, access token, 2FA code, government ID,
or unrelated medical information. We may reply with a minimal verification step so
we delete the correct record. This email path is the primary method for WhatsApp
and TikTok end-customer deletions until those platforms provide an equivalent
signed callback that we have enabled.</p>

<h2>4. Tenant / business account deletion</h2>
<p>To delete a Linas AI Tenant account (owner/staff login, Tenant configuration,
and related operational data under our control), email
<a href="mailto:{email}?subject=Linas%20AI%20account%20deletion">{email}</a>
with the subject “Linas AI account deletion” from the account email, and state the
business name used in the Service. We will verify ownership and then delete or
anonymize account data under our control. Removing a Meta authorization alone does
<strong>not</strong> delete the entire Linas AI business account.</p>
<p>Store subscription cancellations (Apple / Google) must also be managed in the
respective store account settings; deleting Linas AI data does not automatically
cancel a store subscription.</p>

<h2>5. What deletion covers</h2>
<p>When completed, deletion covers under our control: platform-scoped social
identifiers tied to the request, stored DM/comment text and AI replies, optional
comment-derived processing records, conversation state, timestamps, matching
social-chat index entries, and — for Tenant account requests — account profile
fields, Tenant knowledge configuration, and channel connection records we store
for that Tenant, except narrow retention noted below.</p>

<h2>6. What deletion does not cover</h2>
<ul>
  <li>copies retained independently by Meta, TikTok, OpenAI or other LLM
  providers, Apple, Google, Stripe, or other processors under their own legal
  obligations;</li>
  <li>content that remains on a Tenant’s Facebook Page, Instagram account,
  WhatsApp thread, or TikTok presence as controlled by that platform;</li>
  <li>records we must retain for security, fraud prevention, accounting, dispute
  resolution, or other legal obligation (we will explain any narrow exception that
  applies to a manual request);</li>
  <li>aggregated analytics that no longer identify the person.</li>
</ul>

<h2>7. Timing</h2>
<p>Authenticated Meta deletion callbacks are processed when received and status is
exposed at the confirmation URL. Manual email requests are handled as promptly as
practical after verification; we aim to complete deletions under our control within
30 days unless a shorter or longer period is required by law or platform rules.</p>

<h2>8. Deauthorization</h2>
<p>Removing the Linas AI app from Meta account settings may revoke the business
connection and stop future message processing for the affected authorization. That
is separate from full Tenant account deletion (see section 4).</p>

<h2>9. Contact</h2>
<p><a href="mailto:{email}">{email}</a></p>
"""
