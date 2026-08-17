"""Git blob materialization must not depend on GNU dd oflag=excl."""

from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def test_helper_materializes_git_blobs_with_excl_open() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert "oflag=excl" not in source
    assert source.count("authorized LB validator blob could not be read") == 1
    assert source.count("authorized release contract blob could not be read") == 1
    assert "os.O_EXCL" in source
