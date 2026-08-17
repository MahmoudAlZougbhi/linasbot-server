"""Remote HA helper invocations must not steal bash -s stdin."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"
HELPER_OPS = (
    "install-release-bundle-cluster",
    "install-lb-attestation-cluster",
    "prepare-live-ha-contract-cluster",
    "orchestrate-confirmed",
    "orchestrate-reconcile",
    "commit-target-confirmed",
    "recover-confirmed",
    "retry-reconcile-confirmed",
)


def _remote_script() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    start = source.index("<<'REMOTE_DEPLOY'")
    end = source.index("          REMOTE_DEPLOY", start + 1)
    return source[start:end]


def test_remote_helper_invocations_redirect_stdin_away_from_bash_s() -> None:
    script = _remote_script()
    for operation in HELPER_OPS:
        needle = f'"$HELPER_PATH" {operation}'
        assert needle in script
        start = script.index(needle)
        after = script[start : start + 900]
        assert "</dev/null" in after, operation
        assert "</dev/null>" not in after, operation
    assert script.count("</dev/null") >= len(HELPER_OPS)
