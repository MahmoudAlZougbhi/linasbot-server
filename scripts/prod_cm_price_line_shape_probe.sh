#!/usr/bin/env bash
# Classify priced-line shapes in production price_files without printing names/amounts/PII.
set -euo pipefail
cd /opt/linasbot
export LINASBOT_DATA_ROOT="${LINASBOT_DATA_ROOT:-/opt/linasbot_data}"

/opt/linasbot/venv/bin/python - <<'PY'
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path("/opt/linasbot_data/content/price_files")
SEP_RE = re.compile(r"[:|=\-–—\|\.]{2,}|\s{2,}|[/\\]")
DIGIT_RE = re.compile(r"\d+(?:[.,]\d{1,2})?")

shapes: Counter[str] = Counter()
examples: dict[str, dict] = {}

def classify(line: str) -> str:
    s = line.strip()
    if not s:
        return "empty"
    has_digit = bool(DIGIT_RE.search(s))
    has_letter = bool(re.search(r"[A-Za-z\u0600-\u06FF]", s))
    if not has_digit:
        return "no_digit"
    if not has_letter:
        return "digits_only"
    # leading amount?
    if re.match(r"^\s*\d", s):
        return "leading_amount"
    # currency glued to amount mid/end
    if re.search(r"\d+\s*(?:\$|USD|€|EUR|LL)\b", s, re.I) or re.search(r"(?:\$|€)\s*\d+", s):
        if re.search(r"[A-Za-z\u0600-\u06FF].+\d", s):
            if SEP_RE.search(s):
                return "name_sep_amount_currency"
            return "name_space_amount_currency"
    if SEP_RE.search(s):
        return "name_sep_amount_maybe"
    # single spaces between tokens ending with number
    if re.search(r"[A-Za-z\u0600-\u06FF].+\s+\d+(?:[.,]\d{1,2})?\s*$", s):
        return "name_space_amount_eol"
    if "\t" in s:
        return "tab_separated"
    return "other_with_digit"

for path in sorted(ROOT.glob("*.json")):
    obj = json.loads(path.read_text(encoding="utf-8"))
    content = obj.get("content") if isinstance(obj, dict) else None
    if not isinstance(content, str):
        shapes["no_content_field"] += 1
        continue
    for line in content.splitlines():
        kind = classify(line)
        shapes[kind] += 1
        if kind not in examples:
            # metadata only — never the line text
            examples[kind] = {
                "file_sha16": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                "line_len": len(line),
                "digit_count": len(DIGIT_RE.findall(line)),
                "has_colon": ":" in line,
                "has_dash": bool(re.search(r"[-–—]", line)),
                "has_pipe": "|" in line,
                "has_dollar": "$" in line,
                "has_tab": "\t" in line,
                "arabic_chars": len(re.findall(r"[\u0600-\u06FF]", line)),
                "latin_chars": len(re.findall(r"[A-Za-z]", line)),
                "starts_with_digit": bool(re.match(r"^\s*\d", line)),
                "ends_with_digit_or_currency": bool(re.search(r"(\d|\$|USD|EUR|LL)\s*$", line, re.I)),
            }

print(json.dumps({"shapes": dict(shapes), "shape_meta_examples": examples}, indent=2, ensure_ascii=False))
print("[price-shape] COMPLETE_OK")
PY
