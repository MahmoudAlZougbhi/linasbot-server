"""Labelled QA rows can be listed for purge. Real customer rows stay."""

from __future__ import annotations

import json

from scripts.ops.purge_qa_test_data import candidate_rows, classify_row, main


def test_labelled_lab_rows_match_and_real_channels_stay() -> None:
    rows = [
        {"id": "1", "tenant_id": "linas", "channel": "brains_test", "payload": "QA-LINAS-R4 jade-lynx"},
        {"id": "2", "tenant_id": "linas", "channel": "brains_test", "brain": "owner_copilot", "reply": "cobalt-ember"},
        {"id": "3", "tenant_id": "linas", "channel": "instagram_dm", "reply": "cobalt-ember"},
        {"id": "4", "tenant_id": "linas", "channel": "brains_test", "reply": "hello"},
        {"id": "5", "tenant_id": "linas", "kind": "ledger", "amount": 1},
    ]
    assert [row["id"] for row in candidate_rows(rows)] == ["1", "2"]
    assert classify_row(rows[2]) == "kept-channel"
    assert classify_row(rows[3]) == ""
    assert classify_row(rows[4]) == ""


def test_confirm_requires_the_dry_run_count(capsys) -> None:
    rows = [{"tenant_id": "platform", "channel": "brains_test", "text": "QA-CURSOR hi"}]
    assert main(["--rows-json", json.dumps(rows)]) == 0
    assert main(["--confirm", "--count", "0", "--rows-json", json.dumps(rows)]) == 2
    assert main(["--confirm", "--count", "1", "--rows-json", json.dumps(rows)]) == 0
    assert "deleted" in capsys.readouterr().out
