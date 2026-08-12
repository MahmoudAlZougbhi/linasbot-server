# Monty remaining callers (post Decision #9 — Meta Cloud-only in code/tests)

**Updated:** B1 remediation. Runtime transport is Meta Cloud only. No live Meta cutover.

## Removed / migrated this wave

- `WhatsAppFactory` default = `meta`; refuses `montymobile` / `qiscus` / `360dialog` (no silent fallback)
- Webhook photo/voice: Meta Graph media only
- Template send: Meta Graph via `montymobile_template_service` (module name retained; Monty HTTP removed)
- `config/montymobile_templates.json` **DELETED** → `config/whatsapp_cloud_templates.json`
- Health ready: requires `WHATSAPP_API_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` in production (not Monty key)
- Lab defaults: `meta`

## Intentional leftovers (not runtime transport)

| Path | Why kept |
|------|----------|
| `services/ssrf_guard.py` montymobile.com hosts | SSRF allowlist for any residual outbound URL validation |
| `services/whatsapp_adapters/montymobile_adapter*.py` | Archive on disk; factory create methods raise |
| `services/whatsapp_adapters/qiscus_adapter*.py` | Archive on disk; factory create methods raise |
| `services/whatsapp_adapters/dialog360_adapter.py` | Archive on disk; factory create methods raise |
| `services/whatsapp_cloud/legacy_isolation.py` | Dual-bind guard until live cutover approved |
| `.env.example` `MONTYMOBILE_*` | Ops notes until cutover; not used as factory default |
| `scripts/montymobile_manual_probe.py` | Manual probe only |
| `tests/test_montymobile_*` / webhook parse tests | Archive adapter unit tests |
| Metadata keys `recipient_to_monty` / `monty_message_id` | Stable Live Chat metadata keys (values from Cloud send) |

## Callers of template service (now Cloud Graph)

- `modules/smart_messaging_api_send_template.py`
- `services/smart_messaging_deliver.py`
- `services/human_takeover_notification_service.py`

## Not done (out of scope / other agents)

- Live Meta cutover / secret rotation
- Deploy / docker-compose Monty env vars (owned by other agents)
