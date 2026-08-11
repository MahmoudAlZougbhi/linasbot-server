#!/usr/bin/env python3
"""Fail if any hand-written tracked file exceeds 500 physical lines."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

LIMIT = 500
BINARY_EXT = {'.png','.jpg','.jpeg','.gif','.webp','.pdf','.apk','.zip','.ico','.woff','.woff2','.ttf','.eot','.mp4','.mov','.bin'}
GENERATED_NAMES = {'package-lock.json'}
DATA_DUMP_EXT = {'.jsonl'}

def is_generated(rel: str) -> bool:
    name = Path(rel).name
    if name in GENERATED_NAMES or name.endswith('.lock'):
        return True
    return False

def main() -> int:
    raw = subprocess.check_output(['git', 'ls-files', '-z'])
    paths = [p.decode() for p in raw.split(b'\0') if p]
    offenders = []
    for rel in paths:
        if is_generated(rel):
            continue
        ext = Path(rel).suffix.lower()
        if ext in BINARY_EXT or ext in DATA_DUMP_EXT:
            continue
        p = Path(rel)
        if not p.is_file():
            continue
        data = p.read_bytes()
        if b'\0' in data[:4096]:
            continue
        lines = data.count(b'\n') + (0 if data.endswith(b'\n') or not data else 1)
        if lines > LIMIT:
            offenders.append((lines, rel))
    offenders.sort(reverse=True)
    if offenders:
        print(f'FAIL: {len(offenders)} hand-written file(s) over {LIMIT} lines:')
        for n, rel in offenders[:50]:
            print(f'  {n:5d}  {rel}')
        if len(offenders) > 50:
            print(f'  ... +{len(offenders)-50} more')
        return 1
    print(f'OK: 0 hand-written tracked files over {LIMIT} lines')
    return 0

if __name__ == '__main__':
    sys.exit(main())
