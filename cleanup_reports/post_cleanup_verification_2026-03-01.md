# Post-Cleanup Verification Report 2026-03-01

## Preserved Unique Files
- `/Users/mahmoudalzougbhi/linas ai bot/modules/content_files_api.py`: OK
- `/Users/mahmoudalzougbhi/linas ai bot/services/content_files_service.py`: OK
- `/Users/mahmoudalzougbhi/linas ai bot/services/faq_translation_service.py`: OK
- `/Users/mahmoudalzougbhi/linas ai bot/services/smart_retrieval_service.py`: OK
- `/Users/mahmoudalzougbhi/linas ai bot/services/retrieval_debug.py`: OK
- `/Users/mahmoudalzougbhi/linas ai bot/dashboard/src/components/ContentFilesPanel.js`: OK
- `/Users/mahmoudalzougbhi/linas ai bot/data/firebase_data.json`: OK

## Archived Items (Phase 3)
- Moved files count: `12`
- `/Users/mahmoudalzougbhi/linas ai bot/reports_log.jsonl` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/duplicates/reports_log.jsonl`
- `/Users/mahmoudalzougbhi/linas ai bot/conversation_log.jsonl` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/duplicates/conversation_log.jsonl`
- `/Users/mahmoudalzougbhi/linas ai bot/data/style_guide_backup_20260115_112923.txt` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/backup_variants/data/style_guide_backup_20260115_112923.txt`
- `/Users/mahmoudalzougbhi/linas ai bot/data/style_guide_backup_20260116_191526.txt` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/backup_variants/data/style_guide_backup_20260116_191526.txt`
- `/Users/mahmoudalzougbhi/linas ai bot/data/knowledge_base_backup_20260116_191704.txt` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/backup_variants/data/knowledge_base_backup_20260116_191704.txt`
- `/Users/mahmoudalzougbhi/linas ai bot/analyze_knowledge_base.py` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/unused_scripts/analyze_knowledge_base.py`
- `/Users/mahmoudalzougbhi/linas ai bot/check_routes.py` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/unused_scripts/check_routes.py`
- `/Users/mahmoudalzougbhi/linas ai bot/check_template_names.py` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/unused_scripts/check_template_names.py`
- `/Users/mahmoudalzougbhi/linas ai bot/debug_routes.py` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/unused_scripts/debug_routes.py`
- `/Users/mahmoudalzougbhi/linas ai bot/live_chat_endpoints.py` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/unused_scripts/live_chat_endpoints.py`
- `/Users/mahmoudalzougbhi/linas ai bot/add_missing_qas.py` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/unused_scripts/add_missing_qas.py`
- `/Users/mahmoudalzougbhi/linas ai bot/migrate_qa_to_database.py` -> `/Users/mahmoudalzougbhi/linas ai bot/_archive_cleanup_2026-03-01/unused_scripts/migrate_qa_to_database.py`

## Legacy Folder Archive Status
- Legacy source removed from root: `True`
- Legacy archived exists: `True`

## Runtime/Reference Checks
- No references found in `main.py`, `modules/`, `services/`, `routes/`, `handlers/` to archived script names.
- No references found in core runtime paths to `linaslaserbot-2.7.22` or `_archive_cleanup_2026-03-01`.
- Syntax-only compile check passed for active Python files: `105/105` with `0` syntax errors.
- Import smoke check: preserved services import successfully; `main`/`modules.content_files_api` fail due to missing required API env vars (pre-existing configuration requirement).

## Storage Impact
- Current archive size: `1.06 GB` (1086.00 MB)
- Legacy snapshot size inside archive: `1.06 GB` (1085.69 MB)
- Immediate reclaimed disk from move-only strategy: `0` (files were reorganized, not deleted).
- Potential reclaim if archive is permanently deleted later: equal to current archive size above.

## Permanent Deletion
- Not performed. Awaiting explicit approval.