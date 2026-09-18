# `_live_cert/` — isolated QA fixture (not production)

This tree is a **manual** Customer AI certification harness.

- **Not imported** by `main.py`, workers, or HA deploy helpers.
- Tenant id is `v10_live_cert_store` only. It must never write the founder `linas` tenant.
- Seed data is fixture material. It must not run as part of production Save/Publish or prod_migration.
- Production runtime path: owner CM → Luna on Save → Voyage index → customer retrieve → Terra.

To run (local/QA only): `python -m _live_cert.run_live` after `configure()`.
