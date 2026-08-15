"""Sanitized, replacement-free Git source bundle producer for quality gates."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.ha.release_artifact_contract import ContractError, file_evidence

TARGET_SHA_RE = re.compile(r"[0-9a-f]{40}")
MAX_SOURCE_BUNDLE_SIZE = 1024**3
LOCAL_CONFIG_KEYS = frozenset(
    {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "gc.auto",
        "maintenance.auto",
        "remote.origin.url",
        "remote.origin.fetch",
    }
)


def _git_environment(home: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(
    repository: Path,
    home: Path,
    *arguments: str,
    allowed_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=_git_environment(home),
    )
    if result.returncode not in allowed_codes:
        raise ContractError("sanitized Git source-bundle operation failed")
    return result


def _git_bytes(
    repository: Path,
    home: Path,
    *arguments: str,
    allowed_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        env=_git_environment(home),
    )
    if result.returncode not in allowed_codes:
        raise ContractError("sanitized Git source-bundle operation failed")
    return result


def _checkout_identity(repository: Path, git_home: Path, target_sha: str) -> str:
    git_dir_raw = _git(repository, git_home, "rev-parse", "--path-format=absolute", "--git-dir").stdout
    git_dir = Path(git_dir_raw.strip())
    try:
        git_dir_stat = git_dir.lstat()
    except OSError as exc:
        raise ContractError("checkout Git directory is unavailable") from exc
    if not stat.S_ISDIR(git_dir_stat.st_mode) or stat.S_ISLNK(git_dir_stat.st_mode):
        raise ContractError("checkout Git directory is not a real directory")
    repository_stat = repository.lstat()
    if (
        not stat.S_ISDIR(repository_stat.st_mode)
        or stat.S_ISLNK(repository_stat.st_mode)
        or git_dir != repository / ".git"
    ):
        raise ContractError("checkout repository root is not canonical")
    config_records = _git(
        repository,
        git_home,
        "config",
        "--local",
        "--null",
        "--list",
        "--no-includes",
    ).stdout.split("\0")
    if config_records[-1] != "":
        raise ContractError("checkout local Git config encoding is invalid")
    config: dict[str, list[str]] = {}
    for record in config_records[:-1]:
        if "\n" not in record:
            raise ContractError("checkout local Git config record is invalid")
        key, value = record.split("\n", 1)
        config.setdefault(key, []).append(value)
    if set(config) - LOCAL_CONFIG_KEYS:
        raise ContractError("checkout contains forbidden local Git config authority")
    required_config = {
        "core.repositoryformatversion": ["0"],
        "core.filemode": ["true"],
        "core.bare": ["false"],
        "core.logallrefupdates": ["true"],
    }
    if any(config.get(key) != value for key, value in required_config.items()):
        raise ContractError("checkout core Git config is not canonical")
    optional_config = {
        "gc.auto": "0",
        "maintenance.auto": "false",
        "remote.origin.fetch": "+refs/heads/*:refs/remotes/origin/*",
    }
    if any(key in config and config[key] != [value] for key, value in optional_config.items()):
        raise ContractError("checkout optional Git config is not canonical")
    if "remote.origin.url" in config:
        remote = config["remote.origin.url"]
        if (
            len(remote) != 1
            or re.fullmatch(
                r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?",
                remote[0],
            )
            is None
        ):
            raise ContractError("checkout remote URL is not canonical")
    top_level = _git(repository, git_home, "rev-parse", "--path-format=absolute", "--show-toplevel").stdout
    if Path(top_level.strip()) != repository:
        raise ContractError("Git validates a different checkout root")
    for relative in ("objects/info/alternates", "info/grafts", "info/attributes"):
        candidate = git_dir / relative
        if candidate.exists() or candidate.is_symlink():
            raise ContractError("checkout uses forbidden alternate, graft, or attribute authority")
    replacements = _git(
        repository,
        git_home,
        "for-each-ref",
        "--format=%(refname)",
        "refs/replace",
    ).stdout
    if replacements:
        raise ContractError("checkout contains forbidden replacement refs")
    if _git(repository, git_home, "rev-parse", "--is-shallow-repository").stdout.strip() != "false":
        raise ContractError("source bundle requires complete reachable history")
    head = _git(repository, git_home, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
    tree = _git(repository, git_home, "rev-parse", "--verify", "HEAD^{tree}").stdout.strip()
    if head != target_sha or TARGET_SHA_RE.fullmatch(tree) is None:
        raise ContractError("checkout HEAD or tree differs from the target authority")
    index_records = _git(repository, git_home, "ls-files", "-v", "-z", "--cached").stdout.split("\0")
    if index_records[-1] != "" or any(len(record) < 3 or not record.startswith("H ") for record in index_records[:-1]):
        raise ContractError("checkout contains forbidden assume-unchanged or skip-worktree index flags")
    status = _git(repository, git_home, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if status:
        raise ContractError("release checkout is not an exact clean HEAD")
    return tree


def assert_clean_checkout(repository: Path, parent: Path, target_sha: str) -> None:
    with tempfile.TemporaryDirectory(prefix="linas-git-home-", dir=parent) as git_home:
        _checkout_identity(repository, Path(git_home), target_sha)


def target_regular_file_authority(
    repository: Path,
    parent: Path,
    target_sha: str,
    relative_paths: Iterable[str],
) -> dict[str, tuple[str, bool]]:
    requested = tuple(relative_paths)
    if not requested or len(requested) != len(set(requested)):
        raise ContractError("target file authority paths are empty or duplicated")
    with tempfile.TemporaryDirectory(prefix="linas-git-home-", dir=parent) as git_home_raw:
        git_home = Path(git_home_raw)
        _checkout_identity(repository, git_home, target_sha)
        evidence: dict[str, tuple[str, bool]] = {}
        for relative in requested:
            parsed = PurePosixPath(relative)
            if (
                not relative
                or parsed.is_absolute()
                or str(parsed) != relative
                or any(part in {"", ".", ".."} for part in parsed.parts)
                or "\\" in relative
            ):
                raise ContractError("target file authority path is unsafe")
            record = _git(
                repository,
                git_home,
                "ls-tree",
                "-z",
                target_sha,
                "--",
                relative,
            ).stdout
            records = record.split("\0")
            if len(records) != 2 or records[-1] != "" or "\t" not in records[0]:
                raise ContractError("target file authority is missing or ambiguous")
            metadata, observed_path = records[0].split("\t", 1)
            fields = metadata.split(" ")
            if (
                observed_path != relative
                or len(fields) != 3
                or fields[0] not in {"100644", "100755"}
                or fields[1] != "blob"
                or TARGET_SHA_RE.fullmatch(fields[2]) is None
            ):
                raise ContractError("target file authority is not a regular tracked blob")
            blob = _git_bytes(repository, git_home, "cat-file", "blob", fields[2]).stdout
            if len(blob) > 16 * 1024**2:
                raise ContractError("target file authority exceeds its size limit")
            evidence[relative] = (hashlib.sha256(blob).hexdigest(), fields[0] == "100755")
        return evidence


def create_source_bundle(repository: Path, bundle: Path, target_sha: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="linas-git-home-", dir=bundle.parent) as git_home_raw:
        git_home = Path(git_home_raw)
        tree = _checkout_identity(repository, git_home, target_sha)
        _git(repository, git_home, "bundle", "create", str(bundle), "HEAD")
        heads = _git(repository, git_home, "bundle", "list-heads", str(bundle)).stdout
        if heads != f"{target_sha} HEAD\n":
            raise ContractError("source bundle does not advertise exactly the target HEAD")
        verification = Path(tempfile.mkdtemp(prefix="linas-bundle-verify-", dir=bundle.parent))
        try:
            _git(verification, git_home, "init", "--bare", ".")
            _git(verification, git_home, "bundle", "verify", str(bundle))
        finally:
            shutil.rmtree(verification, ignore_errors=True)
    bundle_sha256, size = file_evidence(bundle, max_bytes=MAX_SOURCE_BUNDLE_SIZE)
    if size < 1:
        raise ContractError("source bundle output is invalid")
    return {
        "file": "source.bundle",
        "sha256": bundle_sha256,
        "size": size,
        "target_sha": target_sha,
        "target_tree_sha": tree,
        "advertised_ref": "HEAD",
    }
