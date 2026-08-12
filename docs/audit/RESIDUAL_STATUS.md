# Residual status (continuous run)

**Branch:** `chore/project-cleanup-reorg` (ahead of `origin/main`, not deployed)

## LOC gate

`python3 scripts/audit/line_count_gate.py` → **OK: 0 hand-written tracked files over 500 lines.**

Last god-file split: `chat_response_service.py` facade (`74027d8`).

## Not Done yet (program residual)

- Inventory `review_status`: still mostly `UNREVIEWED` (W00 shell; row count must be refreshed vs current `git ls-files`)
- Security items remaining: Redis limiter on branch (prod flag off), upload validation, webhook replay tests, secret/dep scans, already-strong re-verify
- Mobile parity matrix + landing-only web not completed
- WhatsApp Meta Cloud cutover not done (Monty/Qiscus still present, split not deleted)
- Sensitive `data/*.jsonl` still tracked (see `PII_EXPOSURE_REPORT.md`)
- Characterization/regression of the large splits (chat_response, LiveChat, utils) still light

Continue until inventory COMPLETE and remaining program items closed. No auto merge/deploy.
