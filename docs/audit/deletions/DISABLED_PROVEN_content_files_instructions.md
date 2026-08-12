# DISABLED_PROVEN: legacy global content-files + instructions HTTP APIs

**Status:** DISABLED (410 Gone) — routes kept registered for explicit client errors  
**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**Agent:** B2

## Scope

| Module | Former surface | Action |
|---|---|---|
| `modules/content_files_api.py` | `/api/content-files/*`, `/api/retrieval-debug/logs` | All handlers return **410** `CONTENT_FILES_API_GONE` |
| `modules/instructions_api.py` | `/api/instructions/*` | All handlers return **410** `INSTRUCTIONS_API_GONE` |
| `services/content_files_service.py` | runtime library | **Kept** — still used by retrieval/greeting paths |
| `main.py` imports | side-effect register | **Kept** so routes remain and return 410 |

## Dashboard

- No page components called legacy hooks (only defined in `useApiContent.js` / `useApiTraining.js`).
- Removed dead `getContentFiles*` / `getDynamicMessages*` / `getInstructions*` hook methods.
- Product UI already uses tenant CM via `/api/cm/...` in `useApiContent.js`.

## Caller proof (pre-disable)

| Check | Result |
|---|---|
| `rg` `/api/content-files` under `dashboard/src` | Only `useApiContent.js` (removed) |
| `rg` `/api/instructions` under `dashboard/src` | Only `useApiTraining.js` (removed) |
| Mobile | No callers of these paths |
| Runtime service | `content_files_service` still imported by retrieval — HTTP only disabled |

## Why disable (not migrate storage)

Shared global linas-era file stores are **not multi-tenant safe**. Tenant CM (`/api/cm`) is the SaaS SoT. Fail-closed HTTP disable avoids leaving unauthenticated-or-global mutation surfaces.

## Tests

```text
.venv/bin/pytest -q tests/test_endpoint_auth_matrix.py tests/test_wave1_security.py tests/test_product_modules_disabled.py
```
