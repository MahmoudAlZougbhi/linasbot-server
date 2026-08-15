"""Isolated control-plane archive execution without repo helpers or poisoned imports."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.ha import release_artifact_contract as release

ROOT = Path(__file__).resolve().parents[1]

ISOLATED_RUNNER = textwrap.dedent(
    """
    import importlib.util
    import sys
    import types
    from pathlib import Path

    control_root = Path(sys.argv[1])
    checkout_sentinel = Path(sys.argv[2])
    evil_names = (
        "bootstrap_nested_runtime_evidence",
        "bootstrap_nested_runtime_safety",
        "bootstrap_nested_runtime_loader",
        "bootstrap_nested_runtime_quarantine",
        "scripts.ha.bootstrap_nested_runtime_evidence",
        "scripts.ha.bootstrap_nested_runtime_safety",
    )
    for name in evil_names:
        spoof = types.ModuleType(name)
        spoof.__file__ = str(Path.cwd() / "evil.py")
        spoof.__nested_runtime_source_sha256__ = "deadbeef"
        sys.modules[name] = spoof

    if str(control_root) not in sys.path:
        sys.path.insert(0, str(control_root))
    contract_path = control_root / "scripts/ha/bootstrap_meta_ha_contract.py"
    spec = importlib.util.spec_from_file_location("bootstrap_meta_ha_contract_isolated", contract_path)
    if spec is None or spec.loader is None:
        raise SystemExit("bootstrap contract missing from extracted control plane")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if checkout_sentinel.exists():
        raise SystemExit("malicious checkout preempted authenticated nested-runtime load")
    if module._nested.NESTED_RUNTIME_NAME != "linaslaserbot-2.7.22":
        raise SystemExit("nested runtime name mismatch")
    if getattr(module._nested_evidence, "__nested_runtime_source_sha256__", "") == "deadbeef":
        raise SystemExit("authenticated evidence module trusted spoofed digest")
    identity = module._nested_evidence.portable_content_identity({"schema": 1, "present": False})
    if identity.get("present") is not False:
        raise SystemExit("portable content identity failed")
    print("ok")
    """
)


def test_extracted_control_plane_runs_under_isolated_python_without_repo_helpers(
    tmp_path: Path,
) -> None:
    control_root = tmp_path / "control"
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    checkout_sentinel = tmp_path / "checkout-evil-ran"
    evil = f"from pathlib import Path\nPath({str(checkout_sentinel)!r}).write_text('executed')\n" + (
        ROOT / "scripts/ha/bootstrap_nested_runtime_evidence.py"
    ).read_text(encoding="utf-8")
    (checkout / "scripts/ha").mkdir(parents=True)
    (checkout / "scripts/ha/bootstrap_nested_runtime_evidence.py").write_text(evil, encoding="utf-8")

    for relative in release.CONTROL_PLANE_FILES:
        destination = control_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
        destination.chmod(0o755 if relative.endswith(".sh") else 0o644)

    result = subprocess.run(
        [sys.executable, "-B", "-I", "-S", "-c", ISOLATED_RUNNER, str(control_root), str(checkout_sentinel)],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
    assert not checkout_sentinel.exists()
