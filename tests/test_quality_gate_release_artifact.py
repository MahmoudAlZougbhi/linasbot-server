"""Static contracts for Quality Gates release artifact production."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-gates.yml"
MOBILE_PACKAGE = ROOT / "mobile" / "linas-ai" / "package.json"
MOBILE_MANDATORY_STEPS = (
    "Test",
    "Line limit",
    "Mobile secret scan",
    "Expo export (bundle verification)",
    "Expo export iOS (bundle verification)",
)
MOBILE_NODE_TEST_RUNNER = (
    "node --import ./tests/resolveTsSibling.mjs --experimental-strip-types --test tests/*.test.mjs"
)
MOBILE_TEST_SCRIPT = f"npm run typecheck && {MOBILE_NODE_TEST_RUNNER}"
MOBILE_TEST_SCRIPT_MATCH = "mobile scripts.test must equal the reviewed command"
MOBILE_TEST_SCRIPT_SHELL_BYPASS_MATCH = "mobile scripts.test must not use shell bypass tokens"
MOBILE_TEST_STEP_TIMEOUT_MINUTES = 15
MOBILE_TEST_SCRIPT_FORBIDDEN_TOKENS = ("||", ";", "`", "$(", "\n")
SECURITY_WORKFLOW = ROOT / ".github" / "workflows" / "security-checks.yml"
UPLOAD = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
RUNTIME_TREE = "e4f022d45328996d72ed818a4cecca7588b71589b8804735535ecb88a9856afc"


def _workflow() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def _mobile_package() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(MOBILE_PACKAGE.read_text(encoding="utf-8")))


def _assert_mobile_test_script(package: dict[str, Any]) -> None:
    scripts = package.get("scripts") or {}
    test_script = scripts.get("test")
    assert isinstance(test_script, str) and test_script.strip(), "mobile package.json must define scripts.test"
    typecheck_script = scripts.get("typecheck")
    assert typecheck_script == "tsc --noEmit", "mobile package.json must keep scripts.typecheck on tsc --noEmit"
    assert test_script == MOBILE_TEST_SCRIPT, MOBILE_TEST_SCRIPT_MATCH
    for token in MOBILE_TEST_SCRIPT_FORBIDDEN_TOKENS:
        assert token not in test_script, MOBILE_TEST_SCRIPT_SHELL_BYPASS_MATCH


def _assert_mobile_quality_gate_contract(workflow: dict[str, Any], package: dict[str, Any]) -> None:
    mobile = workflow["jobs"]["mobile"]
    assert "if" not in mobile, "mobile job must not be conditional"
    assert mobile.get("continue-on-error") is not True, "mobile job must not continue on error"

    names = [step.get("name") for step in mobile["steps"]]
    assert names.count("Test") == 1, "mobile job must have exactly one Test step"
    npm_test_steps = [
        step for step in mobile["steps"] if isinstance(step.get("run"), str) and "npm test" in step["run"]
    ]
    assert len(npm_test_steps) == 1, "mobile job must run npm test exactly once"
    assert npm_test_steps[0].get("name") == "Test", "only the Test step may invoke npm test"

    test_index = names.index("Test")
    android_export = names.index("Expo export (bundle verification)")
    ios_export = names.index("Expo export iOS (bundle verification)")
    assert test_index < android_export < ios_export, "mobile Test must run before Expo exports"

    _assert_mobile_test_script(package)
    test_step = _step(mobile, "Test")
    assert test_step["run"] == "npm test", "mobile Test step must run npm test exactly"
    assert test_step.get("timeout-minutes") == MOBILE_TEST_STEP_TIMEOUT_MINUTES, (
        "mobile Test step must declare timeout-minutes"
    )

    for step_name in MOBILE_MANDATORY_STEPS:
        step = _step(mobile, step_name)
        assert "if" not in step, f"{step_name} must not be conditional"
        assert step.get("continue-on-error") is not True, f"{step_name} must not continue on error"


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
    assert source.count("verify_runtime_archive_layout(Path(sys.argv[1]))") == 3
    release_contract = _step(parsed["jobs"]["release-artifact"], "Assemble and verify closed release artifact")["run"]
    for expected in (
        "linas-production-runtime-contract",
        "sudo -n /usr/bin/install -m 0600 -o root -g root",
        "/usr/bin/python3 -B -I -S",
        "os.umask(0o077)",
        "extract_runtime_archive",
        "verify_runtime_before_use",
    ):
        assert expected in release_contract
    assert release_contract.index("os.umask(0o077)") < release_contract.index(
        "extract_runtime_archive(Path(sys.argv[2])"
    )

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


def test_mobile_job_runs_npm_test_before_exports_and_cannot_skip_it() -> None:
    _assert_mobile_quality_gate_contract(_workflow(), _mobile_package())
    source = WORKFLOW.read_text(encoding="utf-8")
    mobile_block = source.split("  mobile:\n", 1)[1].split("\n  secret-scan:\n", 1)[0]
    assert "npm test" in mobile_block
    assert "npm run typecheck" not in mobile_block


def _mobile_contract_mutations() -> list[tuple[str, Callable[[dict[str, Any], dict[str, Any]], None], str]]:
    def disable_test_step(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        _step(workflow["jobs"]["mobile"], "Test")["if"] = False

    def noop_test_script(_workflow: dict[str, Any], package: dict[str, Any]) -> None:
        package["scripts"]["test"] = "true"

    def reorder_test_after_exports(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        steps = workflow["jobs"]["mobile"]["steps"]
        test_step = _step(workflow["jobs"]["mobile"], "Test")
        steps.remove(test_step)
        steps.append(test_step)

    def runner_only_test_script(_workflow: dict[str, Any], package: dict[str, Any]) -> None:
        package["scripts"]["test"] = MOBILE_NODE_TEST_RUNNER

    def disguised_echo_test_script(_workflow: dict[str, Any], package: dict[str, Any]) -> None:
        package["scripts"]["test"] = f"echo ok && {MOBILE_TEST_SCRIPT}"

    def renamed_test_script(_workflow: dict[str, Any], package: dict[str, Any]) -> None:
        package["scripts"]["tests"] = MOBILE_TEST_SCRIPT
        package["scripts"].pop("test", None)

    def duplicate_npm_test_step(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        steps = workflow["jobs"]["mobile"]["steps"]
        test_index = next(index for index, step in enumerate(steps) if step.get("name") == "Test")
        steps.insert(test_index + 1, {"name": "Shadow npm test", "run": "npm test"})

    def disguised_npm_test_continue(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        _step(workflow["jobs"]["mobile"], "Test")["run"] = "npm test || true"

    def shell_bypass_test_script(_workflow: dict[str, Any], package: dict[str, Any]) -> None:
        package["scripts"]["test"] = f"npm run typecheck || true && {MOBILE_NODE_TEST_RUNNER}"

    def shadow_npm_test_step(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        steps = workflow["jobs"]["mobile"]["steps"]
        test_index = next(index for index, step in enumerate(steps) if step.get("name") == "Test")
        steps.insert(test_index + 1, {"name": "Lint", "run": "npm test || true"})

    def continue_on_error_test(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        _step(workflow["jobs"]["mobile"], "Test")["continue-on-error"] = True

    def drop_test_timeout(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        _step(workflow["jobs"]["mobile"], "Test").pop("timeout-minutes", None)

    def duplicate_hidden_test_step(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        steps = workflow["jobs"]["mobile"]["steps"]
        test_index = next(index for index, step in enumerate(steps) if step.get("name") == "Test")
        steps.insert(
            test_index + 1,
            {"name": "Test", "if": False, "run": "true"},
        )

    def conditional_mobile_job(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        workflow["jobs"]["mobile"]["if"] = False

    def continue_on_error_mobile_job(workflow: dict[str, Any], _package: dict[str, Any]) -> None:
        workflow["jobs"]["mobile"]["continue-on-error"] = True

    return [
        ("disabled Test step (if: false)", disable_test_step, "Test must not be conditional"),
        ("no-op test script (true)", noop_test_script, MOBILE_TEST_SCRIPT_MATCH),
        ("test after exports", reorder_test_after_exports, "mobile Test must run before Expo exports"),
        ("runner-only test script", runner_only_test_script, MOBILE_TEST_SCRIPT_MATCH),
        ("disguised echo before reviewed test script", disguised_echo_test_script, MOBILE_TEST_SCRIPT_MATCH),
        ("renamed test script key", renamed_test_script, "mobile package.json must define scripts.test"),
        ("duplicate npm test step", duplicate_npm_test_step, "mobile job must run npm test exactly once"),
        ("disguised npm test continue", disguised_npm_test_continue, "mobile Test step must run npm test exactly"),
        ("shell-bypass test script", shell_bypass_test_script, MOBILE_TEST_SCRIPT_MATCH),
        ("shadow npm test step", shadow_npm_test_step, "mobile job must run npm test exactly once"),
        ("continue-on-error on Test", continue_on_error_test, "Test must not continue on error"),
        ("missing Test timeout", drop_test_timeout, "mobile Test step must declare timeout-minutes"),
        (
            "duplicate hidden Test step (if: false, no-op)",
            duplicate_hidden_test_step,
            "mobile job must have exactly one Test step",
        ),
        ("conditional mobile job (if: false)", conditional_mobile_job, "mobile job must not be conditional"),
        (
            "continue-on-error on mobile job",
            continue_on_error_mobile_job,
            "mobile job must not continue on error",
        ),
    ]


@pytest.mark.parametrize(
    ("label", "mutator", "match"),
    [(label, mutator, match) for label, mutator, match in _mobile_contract_mutations()],
    ids=[label for label, _, _ in _mobile_contract_mutations()],
)
def test_mobile_quality_gate_contract_rejects_regressions(
    label: str,
    mutator: Callable[[dict[str, Any], dict[str, Any]], None],
    match: str,
) -> None:
    del label
    workflow = copy.deepcopy(_workflow())
    package = copy.deepcopy(_mobile_package())
    mutator(workflow, package)
    with pytest.raises(AssertionError, match=match):
        _assert_mobile_quality_gate_contract(workflow, package)


def test_deploy_readiness_checks_protected_ha_helper_not_retired_entrypoint() -> None:
    readiness = _step(_workflow()["jobs"]["deploy-readiness"], "Document readiness gate (no production deploy)")["run"]
    assert "Standalone deploy.sh is disabled." in readiness
    assert "manual protected .github/workflows/deploy.yml" in readiness
    assert "never derives node-local CM/model values or mutates canonical .env" in readiness
    assert 'cat-file -e "$target_sha:scripts/prod_cm_preserve_durable_flags.sh"' in readiness
    assert "linasbot-worker@' scripts/ha/deploy_meta_release_ha.sh" in readiness
    assert "api/queue/ready' scripts/ha/deploy_meta_release_ha.sh" in readiness
    assert "assert_integration_capability_preflight" in readiness
    assert "scripts/ha/integration_capability_preflight.py" in readiness
    assert "assert_target_platform_readiness_preflight" in readiness
    assert "scripts/ha/target_platform_readiness_preflight.py" in readiness
    assert "prod_cm_preserve_durable_flags.sh' deploy.sh" not in readiness
    assert "linasbot-worker@' deploy.sh" not in readiness
    assert "api/queue/ready' deploy.sh" not in readiness
