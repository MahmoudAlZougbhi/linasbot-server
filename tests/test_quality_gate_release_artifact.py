"""Static contracts for Quality Gates release artifact production."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-gates.yml"
SECURITY_WORKFLOW = ROOT / ".github" / "workflows" / "security-checks.yml"
UPLOAD = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
RUNTIME_TREE = "e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc"


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_backend_downloads_exact_binary_hashed_production_wheelhouse_then_installs_dev() -> None:
    backend = _workflow()["jobs"]["backend"]
    install = _step(backend, "Install dependencies")["run"]
    download = install.index("python -m pip download")
    production_install = install.index("python -m pip install", download)
    development_install = install.index("python -m pip install", production_install + 1)
    assert download < production_install < development_install
    assert install.count("--only-binary=:all:") == 3
    assert install.count("--require-hashes") == 3
    production = install[production_install:development_install]
    assert "--no-index" in production
    assert '--find-links="$wheelhouse"' in production
    assert "-r requirements.lock" in production
    assert "-r requirements-dev.lock" in install[development_install:]
    for identity in ("CPython 3.13.15 cpython-313", "linux-x86_64", "uname -m"):
        assert identity in install

    build = _step(backend, "Build authenticated backend intermediate")["run"]
    assert "release_artifact_cli pack" in build
    assert "wheelhouse.tar" in build
    assert "backend-attestation" in build
    assert "--runtime-archive" in build
    upload = _step(backend, "Upload authenticated backend intermediate")
    assert upload["uses"] == UPLOAD
    assert upload["with"]["name"] == "linasbot-wheelhouse-${{ github.sha }}-${{ github.run_attempt }}"
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["compression-level"] == 0


def test_frontend_builds_and_packages_only_after_every_check() -> None:
    frontend = _workflow()["jobs"]["frontend"]
    names = [step.get("name") for step in frontend["steps"]]
    smoke = names.index("Content Management browser smoke")
    build = names.index("Build production dashboard after checks")
    package = names.index("Build authenticated frontend intermediate")
    upload_index = names.index("Upload authenticated frontend intermediate")
    assert smoke < build < package < upload_index
    package_step = _step(frontend, "Build authenticated frontend intermediate")
    assert package_step["working-directory"] == "."
    for expected in (
        "--source dashboard/build",
        "dashboard-build.tar",
        "frontend-attestation",
        "dashboard/package-lock.json",
        "$(node --version)",
        "$(npm --version)",
    ):
        assert expected in package_step["run"]
    upload = _step(frontend, "Upload authenticated frontend intermediate")
    assert upload["uses"] == UPLOAD
    assert upload["with"]["name"] == "linasbot-dashboard-${{ github.sha }}-${{ github.run_attempt }}"


def test_release_job_downloads_both_intermediates_and_uploads_one_closed_artifact() -> None:
    release = _workflow()["jobs"]["release-artifact"]
    assert release["needs"] == ["backend", "frontend"]
    assert release["permissions"] == {"actions": "read", "contents": "read"}
    checkout = release["steps"][0]
    assert checkout["uses"] == CHECKOUT
    assert checkout["with"] == {
        "ref": "${{ github.sha }}",
        "fetch-depth": 0,
        "persist-credentials": False,
    }
    downloads = [step for step in release["steps"] if step.get("uses") == DOWNLOAD]
    assert len(downloads) == 2
    assert {step["with"]["name"] for step in downloads} == {
        "linasbot-wheelhouse-${{ github.sha }}-${{ github.run_attempt }}",
        "linasbot-dashboard-${{ github.sha }}-${{ github.run_attempt }}",
    }
    assemble = _step(release, "Assemble and verify closed release artifact")["run"]
    for binding in (
        '"$GITHUB_REPOSITORY"',
        '"$GITHUB_WORKFLOW_REF"',
        '"$GITHUB_RUN_ID"',
        '"$GITHUB_RUN_ATTEMPT"',
        '"$GITHUB_SHA"',
        "requirements.lock",
        "requirements-dev.lock",
        "dashboard/package-lock.json",
    ):
        assert binding in assemble
    final_upload = _step(release, "Upload closed release artifact")
    assert final_upload["uses"] == UPLOAD
    assert final_upload["with"]["name"] == "linasbot-release-${{ github.sha }}"
    assert final_upload["with"]["path"] == "${{ runner.temp }}/linasbot-release-${{ github.sha }}"
    assert final_upload["with"]["overwrite"] is True


def test_quality_gate_actions_are_immutable_and_manifest_never_claims_github_artifact_identity() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    parsed = _workflow()
    uses = [step["uses"] for job in parsed["jobs"].values() for step in job["steps"] if "uses" in step]
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)
    assert uses.count(UPLOAD) == 3
    assert uses.count(DOWNLOAD) == 2
    assert "artifact_id" not in source
    assert "artifact_digest" not in source
    assert "${{ secrets." not in source


def test_security_checks_use_only_pinned_read_only_checkout() -> None:
    parsed = yaml.safe_load(SECURITY_WORKFLOW.read_text(encoding="utf-8"))
    assert parsed["permissions"] == {"contents": "read"}
    steps = parsed["jobs"]["secret-scan"]["steps"]
    actions = [step for step in steps if "uses" in step]
    assert actions == [
        {
            "uses": CHECKOUT,
            "with": {"fetch-depth": 1, "persist-credentials": False},
        }
    ]


def test_portable_runtime_self_checks_are_bytecode_free_and_tree_stable() -> None:
    parsed = _workflow()
    source = WORKFLOW.read_text(encoding="utf-8")
    assert f"LINAS_PYTHON_RUNTIME_TREE_SHA256: {RUNTIME_TREE}" in source
    assert "e63f572b11b2cdf1bb9b07abecca61b6f25df5312601d7c6cf55b1139ece4726" not in source

    for job_name, step_name in (
        ("backend", "Install exact production Python runtime"),
        ("release-artifact", "Assemble and verify closed release artifact"),
    ):
        command = _step(parsed["jobs"][job_name], step_name)["run"]
        for expected in (
            "runtime_tree_before=",
            "runtime_count_before=",
            "runtime_tree_after=",
            "runtime_count_after=",
            'test "$runtime_tree_after" = "$runtime_tree_before"',
            'test "$runtime_count_after" = "$runtime_count_before"',
            '"$runtime/bin/python3.13" -B',
        ):
            assert expected in command

    for line in source.splitlines():
        if "scripts.ha.release_artifact_cli" in line:
            assert " -B -m scripts.ha.release_artifact_cli" in line


def test_deploy_readiness_checks_protected_ha_helper_not_retired_entrypoint() -> None:
    readiness = _step(_workflow()["jobs"]["deploy-readiness"], "Document readiness gate (no production deploy)")["run"]
    assert "Standalone deploy.sh is disabled." in readiness
    assert "manual protected .github/workflows/deploy.yml" in readiness
    assert "never derives node-local CM/model values or mutates canonical .env" in readiness
    assert 'cat-file -e "$target_sha:scripts/prod_cm_preserve_durable_flags.sh"' in readiness
    assert "linasbot-worker@' scripts/ha/deploy_meta_release_ha.sh" in readiness
    assert "api/queue/ready' scripts/ha/deploy_meta_release_ha.sh" in readiness
    assert "prod_cm_preserve_durable_flags.sh' deploy.sh" not in readiness
    assert "linasbot-worker@' deploy.sh" not in readiness
    assert "api/queue/ready' deploy.sh" not in readiness
