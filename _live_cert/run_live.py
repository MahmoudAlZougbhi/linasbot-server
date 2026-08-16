"""Real OpenAI Customer AI V10 live cert. Isolated tenant. No Meta/WhatsApp sends."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

WT = Path("/Users/alzoughbi/linasbot-v10-resources-wt")
sys.path.insert(0, str(WT))

from _live_cert.bootstrap import TENANT_ID, configure, load_openai_key  # noqa: E402

PATHS = configure()

from _live_cert.calls import RESULTS, probe_openai, record  # noqa: E402
from _live_cert.scenarios_channels import record_channel_blockers  # noqa: E402
from _live_cert.scenarios_core import run_core_scenarios  # noqa: E402
from _live_cert.scenarios_media import run_media_scenarios  # noqa: E402
from _live_cert.tenant_sections import v10_store_sections  # noqa: E402
from _live_cert.tenant_seed import grant_test_credits, init_sqlite, make_assets, seed_catalog, seed_graphs  # noqa: E402
from tests.cm_test_helpers import publish_test_content  # noqa: E402


def _write_report() -> Path:
    out = PATHS["out"] / "live_report.json"
    key = load_openai_key()
    payload = {
        "tenant_id": TENANT_ID,
        "openai_key_fp": hashlib.sha256(key.encode()).hexdigest()[:16] if key else "",
        "results": RESULTS,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("wrote", out, "scenarios", len(RESULTS), flush=True)
    return out


async def main() -> int:
    import services.credit_ai_gate as credit_ai_gate

    credit_ai_gate.ai_generation_blocked = lambda *_a, **_k: False  # type: ignore[assignment]
    init_sqlite(os.environ["LINAS_WHATSAPP_DATABASE_URL"])
    grant_test_credits()
    assets = make_assets()
    seeded = seed_catalog(assets)
    await publish_test_content(TENANT_ID, v10_store_sections(attachments=seeded.get("attachments")))
    graphs = seed_graphs()
    key = load_openai_key()
    try:
        probe = await probe_openai(key)
        record("openai_connectivity", "REAL OPENAI", **probe)
    except Exception as exc:
        record("openai_connectivity", "BLOCKED", ok=False, blocker=type(exc).__name__, error=str(exc)[:300])
        record_channel_blockers()
        _write_report()
        return 2
    try:
        await run_core_scenarios(graphs=graphs)
        await run_media_scenarios(product=seeded, assets=PATHS["assets"], api_key=key)
        record_channel_blockers()
    except Exception as exc:
        record(
            "scenario_crash",
            "BLOCKED",
            ok=False,
            blocker=type(exc).__name__,
            error=str(exc)[:400],
            tb=traceback.format_exc()[-1500:],
        )
        record_channel_blockers()
        _write_report()
        return 1
    _write_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
