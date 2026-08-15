#!/bin/bash
# Thin trust bootstrap for the digest-bound Managed Postgres firewall transaction.
set -euo pipefail

exec /usr/bin/python3 -B -I -S -c '
import hashlib, os, runpy, stat, sys, tempfile
from pathlib import Path

expected = {
    "managed_pg_firewall.py": "18cee89c9dcccf7b1b97496f37db37a04db4726c54bdbcd2f65df46def4db3b4",
    "managed_pg_firewall_authority.py": "4c2760c2cca889697ca26fb04d56d86aee1eb58e00bdf53c2a31ae9c1c63bb9e",
    "managed_pg_firewall_contract.py": "2a1484309ceec83aa6aca7679a3a6270c462af3f397c48c59db7f3f118bc05b9",
    "managed_pg_firewall_provider.py": "aa7151976a39bcd7ca5a7d79adedbd5c9237c1f0e1e2aaff9e41c57574e452e2",
    "managed_pg_firewall_state.py": "034d38ad53e2afb9f27d95f6bed000f1957e328617feef71ec01b17d606357ba",
}
wrapper = Path(sys.argv[1]).resolve(strict=True)
source_dir = wrapper.parent
directory = source_dir.stat()
if not stat.S_ISDIR(directory.st_mode) or directory.st_uid not in {0, os.geteuid()} or stat.S_IMODE(directory.st_mode) & 0o022:
    raise SystemExit("ERROR: unsafe Managed Postgres firewall control directory")

snapshots = {}
for name, expected_sha256 in expected.items():
    path = source_dir / name
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()} or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o022:
            raise SystemExit("ERROR: unsafe Managed Postgres firewall control file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read((1 << 20) + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > 1 << 20 or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise SystemExit("ERROR: Managed Postgres firewall control digest differs")
    snapshots[name] = payload

with tempfile.TemporaryDirectory(prefix="linas-managed-pg-firewall-", dir="/tmp") as temporary:
    root = Path(temporary)
    root.chmod(0o700)
    for name, payload in snapshots.items():
        destination = root / name
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    sys.path.insert(0, str(root))
    sys.argv = ["managed_pg_firewall", *sys.argv[2:]]
    runpy.run_module("managed_pg_firewall", run_name="__main__")
' "${BASH_SOURCE[0]}" "$@"
