"""Deploy helper must resolve Git attribute authority with an absolute git-path."""

from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def test_git_attribute_authority_uses_absolute_git_path() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert "rev-parse --path-format=absolute --git-path info/attributes" in source
    assert 'realpath -m "$(git -C "$REPO_DIR" rev-parse --git-path info/attributes)"' not in source
