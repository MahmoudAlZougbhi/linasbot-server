"""Closed HA runtime process env allows exact systemd PWD and C.UTF-8 locale."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ha.cluster_runtime_env_contract import verify_process_environment

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _canonical_process(extra: bytes = b"") -> bytes:
    return (
        b"OPENAI_API_KEY=expected\0META_DELETION_NODE_ID=node01\0"
        b"LINAS_HA_PEER_HOST=10.106.0.4\0PYTHONUNBUFFERED=1\0"
        b"PYTHONDONTWRITEBYTECODE=1\0"
        b"PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin\0"
        b"HOME=/root\0USER=root\0LOGNAME=root\0" + extra
    )


def test_unit_file_contract_accepts_linasbot_alias() -> None:
    contract = _helper()
    body = contract[contract.index("assert_unit_file_contract() {") : contract.index("assert_unit_contract() {")]
    assert 'if [ "$unit" = linasbot ]; then' in body
    assert "unit=linasbot.service" in body
    assert "linasbot.service)" in body


def test_helper_allows_exact_systemd_pwd_and_c_utf8_locale() -> None:
    helper = _helper()
    assert '"LANG": "C.UTF-8"' in helper
    assert '"LC_ALL": "C.UTF-8"' in helper
    assert '"PWD": str(repo)' in helper
    assert helper.count('"PWD": str(repo)') == 2


def test_process_projection_accepts_systemd_pwd_and_c_utf8_locale(tmp_path: Path) -> None:
    process = tmp_path / "environ"
    process.write_bytes(_canonical_process(b"LANG=C.UTF-8\0LC_ALL=C.UTF-8\0PWD=/opt/linasbot\0"))
    verify_process_environment({"OPENAI_API_KEY": "expected"}, process, node_id="node01")


def test_process_projection_accepts_posix_root_shells(tmp_path: Path) -> None:
    process = tmp_path / "environ"
    for shell in (b"/bin/bash", b"/bin/sh", b"/usr/bin/bash", b"/usr/sbin/nologin"):
        process.write_bytes(
            b"OPENAI_API_KEY=expected\0META_DELETION_NODE_ID=node01\0"
            b"LINAS_HA_PEER_HOST=10.106.0.4\0PYTHONUNBUFFERED=1\0"
            b"PYTHONDONTWRITEBYTECODE=1\0"
            b"PATH=/opt/linasbot/venv/bin:/usr/local/bin:/usr/bin:/bin\0"
            b"HOME=/root\0USER=root\0LOGNAME=root\0SHELL=" + shell + b"\0"
        )
        verify_process_environment({"OPENAI_API_KEY": "expected"}, process, node_id="node01")


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        (b"LANG=en_US.UTF-8\0", "invalid root identity"),
        (b"PWD=/tmp\0", "invalid root identity"),
        (b"SHELL=/tmp/evil\0", r"invalid root identity: SHELL=/tmp/evil"),
        (b"WHATSAPP_DISABLED=true\0", "unauthorized extra key: WHATSAPP_DISABLED"),
    ],
)
def test_process_projection_rejects_noncanonical_os_or_app_keys(tmp_path: Path, extra: bytes, match: str) -> None:
    process = tmp_path / "environ"
    process.write_bytes(_canonical_process(extra))
    with pytest.raises(RuntimeError, match=match):
        verify_process_environment({"OPENAI_API_KEY": "expected"}, process, node_id="node01")
