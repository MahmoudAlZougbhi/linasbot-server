"""Peer helper staging must capture only a closed /run path."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"
HELPER_ROOT_RE = re.compile(r"^/run/linasbot-release-helper\.[A-Za-z0-9]{8}$")


def _function_body(name: str, terminator: str) -> str:
    source = HELPER.read_text(encoding="utf-8")
    start = source.index(f"{name}() {{")
    end = source.index(f"\n{terminator}", start)
    return source[start:end]


def test_prepare_verifies_peer_helper_over_bash_stdin() -> None:
    body = _function_body("prepare_remote_exact_helper", "cleanup_remote_exact_helper() {")
    assert 'scp -q "${SSH_OPTIONS[@]}" -- "$0" "root@${peer_host}:$remote_helper"' in body
    assert 'peer_root_bash_s "$peer_host" "$remote_helper" "$helper_hash"' in body
    assert "/bin/bash --noprofile --norc -s --" in _function_body(
        "peer_root_bash_s", "reap_stale_peer_release_staging() {"
    )
    assert 'awk "{print' not in body
    printf_index = body.index("printf '%s\\n' \"$remote_root\"")
    verify_index = body.index("peer_root_bash_s")
    assert verify_index < printf_index
    assert body.rstrip().endswith("printf '%s\\n' \"$remote_root\"\n}")


def test_cluster_import_reaps_stale_volatile_peer_staging() -> None:
    body = _function_body("install_release_bundle_cluster", "install_lb_ready_attestation_cluster() {")
    assert 'reap_stale_peer_release_staging "$peer_host"' in body
    reap = _function_body("reap_stale_peer_release_staging", "prepare_remote_exact_helper() {")
    assert "/run/linasbot-release-import.????????" in reap
    assert "/run/linasbot-release-helper.????????" in reap


def test_helper_root_contract_rejects_scp_progress_pollution() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert source.count(r"^/run/linasbot-release-helper\.[A-Za-z0-9]{8}$") >= 4
    script = r"""
    set -euo pipefail
    ok=/run/linasbot-release-helper.aB3dE9fG
    [[ "$ok" =~ ^/run/linasbot-release-helper\.[A-Za-z0-9]{8}$ ]]
    bad=$'/run/linasbot-release-helper.aB3dE9fG\nprogress'
    if [[ "$bad" =~ ^/run/linasbot-release-helper\.[A-Za-z0-9]{8}$ ]]; then
      exit 2
    fi
    empty=
    if [[ "$empty" =~ ^/run/linasbot-release-helper\.[A-Za-z0-9]{8}$ ]]; then
      exit 3
    fi
    """
    completed = subprocess.run(
        ["/bin/bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 0, completed.stderr
    assert HELPER_ROOT_RE.fullmatch("/run/linasbot-release-helper.aB3dE9fG")
    assert HELPER_ROOT_RE.fullmatch("/run/linasbot-release-helper.aB3dE9fG\nprogress") is None
