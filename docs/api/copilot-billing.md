# Copilot billing contract

This contract is off until `LINAS_FLAG_COPILOT_PRICING_V2=on`. Customer chats never receive `billing_confirm`.

## Estimate

When the high end of the range is above the approval threshold, the turn does not run. The stream emits:

```json
{
  "type": "billing_confirm",
  "estimate_id": "…",
  "messages_low": 4,
  "messages_high": 7,
  "tokens_low": 25000,
  "tokens_high": 45000,
  "expected_tools": 12,
  "plan_remaining": 24945,
  "purchased_remaining": 0,
  "expires_at": "…",
  "copy": {"en": "…", "ar": "…", "fr": "…"}
}
```

## Decisions

- `POST /api/owner-copilot/estimates/{id}/decline` charges 0.
- `POST /api/owner-copilot/estimates/{id}/approve` runs the turn and charges `clamp(band(actual tokens), min, portal max)`.
- An expired estimate returns 410. A second approve returns the same charge.

## Done event

`charged_messages`, `actual_tokens`, `estimate_low`, `estimate_high`.

The mobile card is a later release. The portal pricing screen is `Copilot pricing`.
