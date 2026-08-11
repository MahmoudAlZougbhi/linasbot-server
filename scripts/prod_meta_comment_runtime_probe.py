#!/usr/bin/env python3
"""Read-only redacted probe for Meta comment webhook delivery (no tokens/content)."""

from __future__ import annotations

import glob
import re
import subprocess
from collections import Counter
from pathlib import Path


def _read_tail(path: Path, *, max_bytes: int = 4_000_000) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def main() -> None:
    journal = subprocess.run(
        ["journalctl", "-u", "linasbot", "--since", "7 days ago", "--no-pager", "-o", "cat"],
        check=False,
        capture_output=True,
        text=True,
    )
    lines = journal.stdout.splitlines()
    for pattern in (
        "/var/log/linasbot.log",
        "/var/log/linasbot.error.log",
        "/var/log/nginx/access.log",
        "/var/log/nginx/error.log",
        "/opt/linasbot/logs/*",
    ):
        for raw in glob.glob(pattern):
            path = Path(raw)
            if path.is_file():
                lines.extend(_read_tail(path))

    patterns = {
        "ig_login_webhook_auth": r"\[instagram-login\] webhook_authenticated",
        "ig_login_comments_nonzero": r"\[instagram-login\] webhook_authenticated .* comments=[1-9]\d*",
        "meta_comment_webhook_auth": r"\[meta-comment\] webhook_authenticated",
        "meta_comment_events_dropped": r"\[meta-comment\] events_dropped",
        "meta_comment_started": r"\[meta-comment\] event_processing_started",
        "meta_comment_completed": r"\[meta-comment\] event_processing_completed",
        "meta_comment_failed": r"\[meta-comment\] event_processing_failed",
        "meta_comment_reply_sent": r"\[meta-comment\] reply_sent",
        "meta_comment_reply_failed": r"\[meta-comment\] reply_failed",
        "meta_comment_private_reply": r"\[meta-comment\] private_reply",
        "ig_login_background_fail": r"\[instagram-login\] background_processing_failed",
        "nginx_ig_login_post": r"POST /webhook/instagram-login",
        "nginx_meta_messaging_post": r"POST /webhook/meta-messaging",
    }
    counts = Counter(
        name for line in lines for name, pattern in patterns.items() if re.search(pattern, line, re.IGNORECASE)
    )
    print(f"[comment-probe] journal_exit={journal.returncode} scanned_lines={len(lines)}")
    for name in sorted(patterns):
        print(f"[comment-probe] {name}={counts[name]}")

    status_reasons: Counter[str] = Counter()
    for line in lines:
        match = re.search(
            r"\[meta-comment\] event_processing_completed channel=(\w+) status=(\w+) reason=([^\s]+)",
            line,
        )
        if match:
            status_reasons[f"{match.group(1)}:{match.group(2)}:{match.group(3)}"] += 1
        drop = re.search(
            r"\[meta-comment\] events_dropped object=(\w+) raw=(\d+) resolved=0 bindings=(\d+) reasons=(\{.*\})",
            line,
        )
        if drop:
            print(
                f"[comment-probe] drop object={drop.group(1)} raw={drop.group(2)} "
                f"bindings={drop.group(3)} reasons={drop.group(4)}"
            )
        ig = re.search(
            r"\[instagram-login\] webhook_authenticated object=(\w+) parsed=(\d+) "
            r"accepted=(\d+) duplicates=(\d+) comments=(\d+)",
            line,
        )
        if ig and int(ig.group(5)) > 0:
            print(
                f"[comment-probe] ig_login_comments object={ig.group(1)} "
                f"parsed={ig.group(2)} accepted={ig.group(3)} comments={ig.group(5)}"
            )
        mc = re.search(
            r"\[meta-comment\] webhook_authenticated object=(\w+) raw=(\d+) "
            r"parsed=(\d+) accepted=(\d+) duplicates=(\d+)",
            line,
        )
        if mc:
            print(
                f"[comment-probe] meta_comment_auth object={mc.group(1)} raw={mc.group(2)} "
                f"parsed={mc.group(3)} accepted={mc.group(4)}"
            )

    print(f"[comment-probe] completed_status_variants={len(status_reasons)}")
    for key, count in sorted(status_reasons.items()):
        print(f"[comment-probe] completed {key} occurrences={count}")
    print("[comment-probe] SUCCESS")


if __name__ == "__main__":
    main()
