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
- `TIKTOK_ADS_APP_ID` / `TIKTOK_ADS_APP_SECRET` — optional Marketing API overrides; default to the Accounts client key/secret
- `TIKTOK_ADS_REDIRECT_URI` — default `https://www.linasaibot.com/oauth/tiktok/ads/callback`

Production redirect URL for the TikTok developer portal:

`https://www.linasaibot.com/oauth/tiktok/callback`

Marketing API advertiser redirect URL (Enhanced Video Context):

`https://www.linasaibot.com/oauth/tiktok/ads/callback`

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

Enhanced Video Context is a second, optional Marketing API grant. Accounts connect/comments stay on the account-holder token. After TikTok approves Query Identity + Business Center Asset, the tenant runs Enable Enhanced Video Context from Integrations. Preview media URLs are never stored. `full_video` is only set after an official URL is processed by the existing comment video pipeline.
