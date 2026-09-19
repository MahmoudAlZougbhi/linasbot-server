"""Other-runtime dead islands stay gone; live scale/queue cores stay present."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE_PATHS = (
    "utils/datetime_intents.py",
    "utils/datetime_utils.py",
    "services/scale/replica_health.py",
    "services/scale/ai_stage_timing.py",
    "services/scale/ha_peer_file_replicate.py",
    "services/scale/financial_invariants.py",
    "services/safe_path.py",
)

KEEP_PATHS = (
    "services/scale/isolated_replica_pool.py",
    "services/scale/self_heal.py",
    "services/scale/ha_cm_peer_replicate.py",
    "services/scale/ha_tenant_config_peer_sync.py",
    "services/scale/replica_controller.py",
    "services/queues/handlers.py",
    "services/queues/worker_runtime.py",
    "scripts/run_queue_worker.py",
    "utils/utils.py",
)


def test_dead_other_runtime_paths_are_gone() -> None:
    for rel in GONE_PATHS:
        assert not (ROOT / rel).exists(), rel


def test_active_other_runtime_cores_remain() -> None:
    for rel in KEEP_PATHS:
        assert (ROOT / rel).is_file(), rel


def test_repo_has_no_imports_of_deleted_runtime_modules() -> None:
    needles = (
        "from services.safe_path import",
        "import services.safe_path",
        "from utils.datetime_intents import",
        "from utils.datetime_utils import",
        "from services.scale.replica_health import",
        "from services.scale.ai_stage_timing import",
        "from services.scale.ha_peer_file_replicate import",
        "from services.scale.financial_invariants import",
    )
    skip_parts = ("/node_modules/", "/.git/", "/evals/artifacts/", "tests/test_runtime_dead_gone.py")
    for path in ROOT.rglob("*.py"):
        text = str(path)
        if any(part in text for part in skip_parts):
            continue
        blob = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in blob, f"{path}: {needle}"
