"""Official HA deploy retries GitHub artifact 503 without skipping digest proof."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"


def test_release_artifact_download_retries_github_503_with_digest() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    download = source[
        source.index("      - name: Download exact immutable release artifact ID") : source.index(
            "      - name: Retry exact immutable release artifact download"
        )
    ]
    retry = source[
        source.index("      - name: Retry exact immutable release artifact download") : source.index(
            "      - name: Validate release bundle and extract exact helper"
        )
    ]
    assert "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in download
    assert "artifact-ids: ${{ inputs.RELEASE_ARTIFACT_ID }}" in download
    assert "continue-on-error: true" in download
    assert "id: download_release" in download
    assert "steps.download_release.outcome == 'failure'" in retry
    assert "actions/artifacts/${RELEASE_ARTIFACT_ID}/zip" in retry
    assert "retried release artifact zip digest is not the GitHub authority" in retry
    assert "curl" not in retry
    assert "wget" not in retry
    assert "RELEASE_ARTIFACT_API_SHA256" in retry
