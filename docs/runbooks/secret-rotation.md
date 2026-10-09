# Secret rotation

Rotate one secret at a time on production. Turn the new value on for `qa-linas` first, then the rest of production, and keep the previous value only for the overlap the provider allows.

| Secret | Overlap |
|---|---|
| Postgres password | Create the new role password, switch `app_rw`, then drop the old password. |
| Valkey password | Add the new ACL user, switch `REDIS_URL`, then delete the old user. |
| Meta app secret and page tokens | Add the new secret in the Meta app, update the webhook, then remove the old one. |
| TikTok client secret | Same pattern as Meta. |
| Apple and Google OAuth / IAP keys | Publish the new key, keep the old verification key until stored tokens expire. |
| OpenAI and Voyage keys | Create a new key, switch the env, revoke the old key. |
| Resend | New API key, then revoke. |
| Stripe | Roll the secret key in Stripe, update the webhook signing secret, then revoke. |
| JWT signing key | Add a new `kid`, sign new tokens with it, accept the previous `kid` until those tokens expire, then remove it. |

Never print a value in CI logs, chat, or a pull request. Names live in the secrets manager. Kubernetes receives them through External Secrets, not through an image or a `.env` file.
