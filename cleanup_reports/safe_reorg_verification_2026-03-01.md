# Safe Reorganization Verification Report 2026-03-01

## Move Verification
- Verified moved files: `12/12`
- Frontend archived: `True`

## Runtime-Sensitive Paths
- main_py_exists: `True`
- deploy_sh_exists: `True`
- workflow_deploy_exists: `True`
- main_references_dashboard_build: `True`

## Stale Reference Scan
- Hits found (excluding archive/reports): `0`

## Syntax Check
- Python files compiled (syntax-only): `105`
- Syntax errors: `0`

## Import Smoke Check
- `main`: FAIL (ValueError: Missing API credentials: LINASLASER_API_BASE_URL or LINASLASER_API_TOKEN)
- `modules.content_files_api`: FAIL (ValueError: Missing API credentials: LINASLASER_API_BASE_URL or LINASLASER_API_TOKEN)
- `services.content_files_service`: OK
- `services.faq_translation_service`: OK
- `services.smart_retrieval_service`: OK
- `services.retrieval_debug`: OK

## Residual Risks
- `docker-compose.yml` still defines a `frontend` service with `context: ./frontend`; since `frontend/` is archived, this compose path is now stale unless updated later.
- `main` import requires environment credentials (existing behavior), so full runtime start still depends on `.env` values.

## Result
- Safe reorganization completed with runtime-critical backend layout unchanged (`main.py`, `modules/`, `services/`, `handlers/`, `routes/`).