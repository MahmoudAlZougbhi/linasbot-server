# TikTok Business (Linas AI)

Env var **names** only — never put secret values in git.

Required for OAuth / API / webhook signature:

- `TIKTOK_CLIENT_KEY` — TikTok app client key / App ID
- `TIKTOK_CLIENT_SECRET` — TikTok app secret (also HMAC key for `TikTok-Signature`)
- `META_CREDENTIAL_ENCRYPTION_KEY` — existing AES-GCM key used to encrypt tokens at rest
- `DATABASE_URL` or `LINAS_WHATSAPP_DATABASE_URL` — PostgreSQL SoT (same as other Linas PG tables)

Optional:

- `TIKTOK_REDIRECT_URI` — default `https://www.linasaibot.com/oauth/tiktok/callback`
- `TIKTOK_WEBHOOK_CALLBACK_URL` — default `https://www.linasaibot.com/webhooks/tiktok`

Production redirect URL for the TikTok developer portal:

`https://www.linasaibot.com/oauth/tiktok/callback`

Webhook callback URL:

`https://www.linasaibot.com/webhooks/tiktok`

(alias: `https://www.linasaibot.com/webhook/tiktok`)

Requested TikTok Accounts scopes only:

- Get Account User Basic Info (`user.info.basic`)
- Get Account Media (`video.list`)
- Get Account Comment (`comment.list`)
- Manage Account Comment (`comment.list.manage`)
- Auth Code Management (`biz.spark.auth`)

Business Messaging is **code-complete and capability-gated**. It is not requested in OAuth. Until TikTok approves Business Messaging and the token includes `message.list.read` plus send/manage, DMs show Permission pending. Data Portability is never used as a messaging substitute.

Missing `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` fails closed for connect and webhooks. `/api/ready` reports capability without requiring those credentials (TikTok is optional until configured).
