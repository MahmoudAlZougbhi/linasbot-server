# CM Full Corpus Ledger (Phase 0 — local + code inventory)

Generated as part of `feat/cm-full-corpus-no-scrub`. Production machine ledger is produced by
`scripts/prod_cm_corpus_inventory.sh` after deploy (metadata only: path, sha256, size, category).

## Root cause of prior over-scrub

`services/cm/prod_migration.py` ran `scrub_restricted_affirmations()` after every production
migration. That function used hardcoded `UNSUPPORTED_TOPIC_MARKERS` (tattoo / CO₂ /
pigmentation / facial) plus `INITIAL_RESTRICTED_TOPIC_IDS` to mark matching FAQ and knowledge
rows as `status=restricted`, excluding them from AI retrieval and dumping topic-named articles
into Restricted. Owner rule now: recover every original Lina file; Restricted Topics remain an
owner-configured platform feature only.

## Code corrections in this branch

- Keyword scrub disabled; `restore_keyword_scrubbed_content` reactivates scrubbed rows
- Migration seeds empty Restricted policy (no auto-restrict)
- Stage + import `style_files/`, `dynamic_messages.json`
- Full `system_prompt_template.txt` → `ai_basics.advanced_instructions` (not truncated notes)
- Knowledge file filename + checksum attached on migrate
- Testing Lab returns `cm_diagnostics` with `source_ids` / retrieved source titles
- Owner forms from PR #42 kept (CmAiBasicsPage and section forms present)

## Locations searched (local)

| Root | Role |
|------|------|
| `/Users/alzoughbi/linasbot-server-cm-control-plane/data` | Repo sample content |
| `/Users/alzoughbi/linasbot-server-cm-control-plane/linasbot_data` | Local persistent layout |
| `/Users/alzoughbi/linasbot-server/data` | Sibling sample |
| `/Users/alzoughbi/linasbot-server/linasbot_data` | Sibling persistent |
| `.cm_td*/tenants/*/cm/archive/restricted_scrub/` | Scrub archives (faq_removed etc.) |
| `tests/fixtures/cm_migration/legacy/` | Fixture corpus |
| Production (via workflow after deploy) | `/opt/linasbot/data`, `/opt/linasbot_data`, `/opt/linasbot_backups/cm/` |

## Production verification (post-deploy)

1. Workflow `CM Production Cutover` → `backup`
2. → `corpus_inventory` (writes `/opt/linasbot_backups/cm/inventory/corpus_ledger_*.json`)
3. → `migrate_validate` → `publish` → rollback rehearsal → re-publish
4. Confirm tattoo/CO2/whitening knowledge `status=active` and indexed

Do not store secrets or customer message bodies in this document.
