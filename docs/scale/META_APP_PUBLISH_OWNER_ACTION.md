# Meta App Publish — owner action (not server-fixable)

The Linas Meta application being **Unpublished** cannot be fixed by server code or deployment.

## Behavior matrix

| Scenario | What happens |
|----------|----------------|
| Meta Dashboard **feed → Test** | Synthetic webhook only. Proves callback URL + signature + parser. Does **not** prove real Page comment delivery. |
| Real Facebook comment (production Page) | Requires the Meta app to be **Published**. Until then, rely on Graph polling fallback (~1 min). |
| Mahmoud account after Publish | Works under **Standard Access** / App Role tester rules. |
| Ordinary customers (non-role) | Require **Advanced Access** for live comment/DM delivery at scale. |

## Server responsibilities (already implemented)

- `include_values=true` on Page app webhook subscription (Connect, reconcile, recovery).
- Signed webhook ingress logging (`[meta-webhook]`, `[meta-comment]`) without secrets or customer content.
- Graph polling fallback with shared Postgres cursors and durable dedupe.
- Postgres SoT for channel toggles, per-asset comment settings, and CM published actions.

## Owner checklist (Meta Dashboard)

1. Complete App Review requirements for `pages_messaging`, `pages_read_engagement`, comment scopes as needed.
2. **Publish** the app when ready for non-tester production traffic.
3. Keep Page subscribed fields: `feed`, `messages`, `messaging_postbacks`, `standby` with `include_values=true`.
4. Use Dashboard **Test** only to validate webhook plumbing — not as proof of live comment AI.
