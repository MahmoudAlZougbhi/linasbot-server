# Firestore indexes — deploy checklist (owner-activated)

**Repo source of truth:** `firestore.indexes.json` (project root)  
**Human index notes:** `docs/FIRESTORE_INDEXES.md`

## Important

- This document is a **checklist only**.
- **Do not** deploy Firestore indexes from CI without an explicit owner
  activation (Mahmoud). There is intentionally **no** automatic
  `firebase deploy --only firestore:indexes` step in `.github/workflows`
  that runs on every push.
- LIVE deploy of indexes is **owner-activated** after verifying the JSON
  matches production query shapes (especially `live_chat_index`).

## When to deploy

1. Composite index errors appear in API/worker logs
   (`The query requires an index…`).
2. Or after intentional changes to `firestore.indexes.json` reviewed in a PR.

## How (manual / owner)

```bash
# From a machine with Firebase CLI + project access:
firebase deploy --only firestore:indexes
```

Or click the console link embedded in the Firestore error (pre-filled index).

## GHA note for future workflow authors

If adding a workflow step:

- Gate with `workflow_dispatch` + typed `CONFIRM=DEPLOY_FIRESTORE_INDEXES`.
- Never run on `push` to `main` by default.
- Prefer documenting here over silent deploys.

## Verify after deploy

- Firebase Console → Firestore → Indexes → status **Enabled**.
- Live Chat list / waiting-queue queries succeed without index errors.
