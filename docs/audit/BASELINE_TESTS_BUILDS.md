# Baseline tests/builds (W00)

**SHA:** `781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26`

## Commands attempted

### pytest wave1_security + webhook_dedupe
```
...........EEEEEEEEE....FFFFF..                                          [100%]
=========================== short test summary info ============================
FAILED tests/test_webhook_dedupe.py::test_webhook_memory_try_claim_first_wins
FAILED tests/test_webhook_dedupe.py::test_text_body_fingerprint_same_for_duplicate_payload_shape
FAILED tests/test_webhook_dedupe.py::test_text_body_fingerprint_empty_for_non_text
FAILED tests/test_webhook_dedupe.py::test_webhook_bodyfp_try_claim_serializes
FAILED tests/test_webhook_dedupe.py::test_webhook_memory_concurrent_only_one_claim
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_protected_get_without_cookie_401
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_health_public
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_docs_disabled_when_flag_set
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_ssrf_endpoint_requires_auth_then_blocks
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_simulate_webhook_disabled
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_social_takeover_forbidden
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_session_idor_blocked
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_csrf_required_on_mutation
ERROR tests/test_wave1_security.py::TestAPIAuthEnforcement::test_role_matrix_viewer_forbidden_users
5 failed, 17 passed, 9 errors in 0.31s
```

## Baseline failures (recorded, not fixed in W00)

- `tests/test_wave1_security.py`: 9 ERRORs in TestAPIAuthEnforcement (environment/app fixture issues during W00 subset run)
- `tests/test_webhook_dedupe.py`: 5 FAILED claim/fingerprint tests

W00 does not change application behavior. Failures are baselines for later waves to clear or confirm env needs.

## Line count gate

`python3 scripts/audit/line_count_gate.py` currently FAILs (expected until split waves complete).
