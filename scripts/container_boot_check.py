"""Smoke check for a read-only container root."""

from pathlib import Path

from services.platform.feature_flags import flag_value
from services.platform.health_checks import live_payload


def main() -> None:
    Path("/tmp/linas-boot").write_text("ok", encoding="utf-8")
    if live_payload()["ok"] is not True:
        raise SystemExit("live check failed")
    if flag_value("queue_backend") != "redis":
        raise SystemExit("queue default changed")
    print("boot-ok")


if __name__ == "__main__":
    main()
