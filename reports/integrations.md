# Integrations

| Integration | Result | Why |
|---|---|---|
| Website chat widget | tested | Unit tests cover a disabled widget and the per-visitor rate-limit key. No live site was called. |
| Meta Facebook and Instagram webhooks | not testable | No sandbox app secret is available. The sandbox store never calls graph.facebook.com. |
| Instagram reconnect | not testable | The live page binding was not changed. |
| WhatsApp Cloud send | not testable | Sending needs an approved test number. Status was not queried. |
| TikTok | not testable | The connected account is the wrong one, and no sandbox token was used. |
| Apple in-app purchase | not testable | No sandbox purchase was made. |
| Google Play billing | not testable | License testers are a later release. |
| Stripe | not testable | No test-mode charge was made. |
| Voyage | not testable | Calling the live API would spend quota. Cache and retry are covered by earlier tests. |
| Model provider | not testable | No live completion was requested. |
| Push notifications | not testable | No test device token was available. |
| Email and support MX | not testable | Live DNS is unchanged. |
| Spaces and CDN | not testable | No Spaces key is configured for this workspace. |
| Cloudflare | not testable | DNS and the proxy were not changed. |
