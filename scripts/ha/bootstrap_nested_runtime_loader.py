"""Path-bound authenticated loader for nested-runtime bootstrap modules."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import sys
from pathlib import Path

READ_CHUNK = 1024 * 1024
MAX_SOURCE_BYTES = 512 * 1024


class NestedRuntimeLoaderError(RuntimeError):
    """Fixed-message failure; source paths are never echoed."""


def _read_source_bytes(path: Path) -> bytes:
    resolved = path.resolve()
    before = resolved.lstat()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not 1 <= before.st_size <= MAX_SOURCE_BYTES
    ):
        raise NestedRuntimeLoaderError("nested runtime loader source is invalid")
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    chunks: list[bytes] = []
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise NestedRuntimeLoaderError("nested runtime loader source is invalid")
        consumed = 0
        while consumed < opened.st_size:
            chunk = os.read(descriptor, min(READ_CHUNK, opened.st_size - consumed))
            if not chunk:
                raise NestedRuntimeLoaderError("nested runtime loader source is invalid")
            chunks.append(chunk)
            consumed += len(chunk)
        after_fd = os.fstat(descriptor)
        if (after_fd.st_dev, after_fd.st_ino, after_fd.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise NestedRuntimeLoaderError("nested runtime loader source changed during load")
        after_path = resolved.lstat()
        if (after_path.st_dev, after_path.st_ino, after_path.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise NestedRuntimeLoaderError("nested runtime loader source changed during load")
    except OSError as exc:
        raise NestedRuntimeLoaderError("nested runtime loader source is invalid") from exc
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def source_sha256(path: Path) -> str:
    return hashlib.sha256(_read_source_bytes(path)).hexdigest()


def authenticated_module_name(logical_name: str, path: Path) -> str:
    return f"{logical_name}@{source_sha256(path.resolve())}"


def load_authenticated_module(logical_name: str, path: Path):  # type: ignore[no-untyped-def]
    resolved = path.resolve()
    digest = source_sha256(resolved)
    module_name = authenticated_module_name(logical_name, resolved)
    cached = sys.modules.get(module_name)
    if cached is not None:
        if (
            getattr(cached, "__file__", None) != str(resolved)
            or getattr(cached, "__nested_runtime_source_sha256__", None) != digest
        ):
            del sys.modules[module_name]
        else:
            return cached
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise NestedRuntimeLoaderError("nested runtime loader source is invalid")
    module = importlib.util.module_from_spec(spec)
    module.__nested_runtime_source_sha256__ = digest  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if getattr(module, "__nested_runtime_source_sha256__", None) != digest:
        raise NestedRuntimeLoaderError("nested runtime loader source changed during load")
    if getattr(module, "__file__", None) != str(resolved):
        raise NestedRuntimeLoaderError("nested runtime loader source is invalid")
    return module
