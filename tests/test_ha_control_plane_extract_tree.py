"""Control-plane extraction must bind the reviewed tree digest."""

from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def test_release_bundle_extracts_control_plane_with_manifest_tree() -> None:
    source = HELPER.read_text(encoding="utf-8")
    start = source.index('die "release control-plane extraction failed closed"')
    snippet = source[source.rfind("<<'PY'", 0, start) : start]
    assert 'control["tree_sha256"]' in snippet
    assert "expected_paths=CONTROL_PLANE_MEMBERS" in snippet
    assert snippet.count("extract_archive(") == 1
    bash = source[source.rfind("control_parent=", 0, start) : start]
    assert 'control_root="$control_parent/tree"' in bash
    assert "mktemp -d -p /run linasbot-control-plane." in bash
    assert "Path(destination)" in snippet
    assert 'control["tree_sha256"]' in snippet
