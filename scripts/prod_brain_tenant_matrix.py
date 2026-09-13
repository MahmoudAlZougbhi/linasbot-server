"""Capture-only production Brain matrix. Does not send WhatsApp or Instagram.

Loads seed/publish/matrix modules from this git ref (via /tmp) or from the app tree.
Overlays greeting-only Brain files in this process only; gunicorn stays on the live SHA.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType


def _load_env(app_dir: Path) -> None:
    os.chdir(app_dir)
    for env_path in (Path("/opt/linasbot/.env"), app_dir / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _module_path(filename: str) -> Path:
    here = Path(__file__).resolve().parent
    dumped = Path("/tmp/live_matrix_pack") / filename
    app_evals = Path("/opt/linasbot/services/customer_ai/evals") / filename
    app_cai = Path("/opt/linasbot/services/customer_ai") / filename
    repo_evals = here.parent / "services" / "customer_ai" / "evals" / filename
    repo_cai = here.parent / "services" / "customer_ai" / filename
    for candidate in (dumped, repo_evals, repo_cai, app_evals, app_cai, here / filename):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(filename)


def _overlay_greeting_path() -> list[str]:
    import services.customer_ai.runtime as runtime

    loaded: list[str] = []
    for name, filename in (
        ("services.customer_ai.greeting", "greeting.py"),
        ("services.customer_ai.templates", "templates.py"),
        ("services.customer_ai.turn_pipeline", "turn_pipeline.py"),
    ):
        path = _module_path(filename)
        _load_module(name, path)
        loaded.append(f"{name}={path}")
    import services.customer_ai.turn_pipeline as pipeline
    from services.customer_ai.billing import apply_message_billing, release_turn_reservation

    async def _run_billed(turn, *, message, channel):
        try:
            return apply_message_billing(
                turn, await pipeline.run_dm_after_gates(turn, message=message, channel=channel)
            )
        except Exception:
            release_turn_reservation(turn)
            raise

    runtime._run_billed = _run_billed
    runtime.run_dm_after_gates = pipeline.run_dm_after_gates
    loaded.append(f"pipeline={pipeline.run_dm_after_gates.__code__.co_filename}")
    return loaded


async def _run() -> dict:
    overlay = _overlay_greeting_path()
    seed_path = _module_path("live_tenant_seed.py")
    publish_path = _module_path("live_tenant_publish.py")
    matrix_path = _module_path("live_tenant_matrix.py")
    print("[tenant-matrix] overlay " + json.dumps(overlay), flush=True)
    print(f"[tenant-matrix] seed={seed_path} publish={publish_path} matrix={matrix_path}", flush=True)
    seed = _load_module("live_tenant_seed", seed_path)
    sys.modules["services.customer_ai.evals.live_tenant_seed"] = seed
    publish = _load_module("live_tenant_publish", publish_path)
    matrix = _load_module("live_tenant_matrix", matrix_path)
    published = await publish.seed_and_publish_all()
    results = await matrix.run_matrix()
    return {"publish": published, "matrix": results, "overlay": overlay}


def main() -> int:
    app_dir = Path(os.environ.get("APP_DIR") or "/opt/linasbot")
    _load_env(app_dir)
    sys.path.insert(0, str(app_dir))
    report = asyncio.run(_run())
    print("[tenant-matrix] " + json.dumps(report, ensure_ascii=False, default=str)[:12000])
    matrix = report.get("matrix") or {}
    ok = bool(matrix.get("ok"))
    print(f"[tenant-matrix] passed={matrix.get('passed')}/{matrix.get('total')} ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
