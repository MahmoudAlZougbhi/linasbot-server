"""Price-row extractors for CM pricing migration (no invented amounts)."""

from __future__ import annotations

import re
from typing import Any

from services.cm.schemas import LocalizedLabels

_AMOUNT_KEYS = (
    "amount",
    "price",
    "unit_price",
    "base_price",
    "cost",
    "final_price",
    "discounted_price",
    "value",
)
_NAME_KEYS = (
    "name",
    "title",
    "label",
    "body_part",
    "service",
    "item",
    "area",
    "body_area",
    "part",
    "machine",
)

# Lines that look like session/schedule guidance, not sellable unit prices.
_SKIP_LINE_RE = re.compile(
    r"(?i)\b("
    r"session|sessions|interval|minimum sessions|"
    r"every\s+\d+|days?\s+apart|do not|selector|pricing rules|"
    r"use prices only|additional relevant context"
    r")\b"
)

# Name + separator + optional currency + amount (optional trailing notes after / or ().
_PRICED_LINE_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z\u0600-\u06FF][^:=\-|\$€£]{0,80}?)\s*"
    r"(?::|=|-|–|—|\.{2,}|\|)\s*"
    r"(?P<cur>\$|€|£|USD|EUR|LL|L\.?L\.?)?\s*"
    r"(?P<amount>\d+(?:[.,]\d{1,2})?)\s*"
    r"(?P<cur2>\$|€|£|USD|EUR|LL|L\.?L\.?)?\b",
    re.IGNORECASE,
)

# Selector style without colon: "Underarms 40$" / "Full legs 120 USD"
_PRICED_SPACE_EOL_RE = re.compile(
    r"^\s*[-•*]?\s*(?P<name>[A-Za-z\u0600-\u06FF][^\$€£\d]{1,80}?)\s+"
    r"(?P<cur>\$|€|£|USD|EUR|LL|L\.?L\.?)?\s*"
    r"(?P<amount>\d+(?:[.,]\d{1,2})?)\s*"
    r"(?P<cur2>\$|€|£|USD|EUR|LL|L\.?L\.?)?\s*$",
    re.IGNORECASE,
)

# Leading amount: "40$ Underarms" / "$40 Underarms"
_PRICED_LEADING_RE = re.compile(
    r"^\s*(?P<cur>\$|€|£|USD|EUR|LL|L\.?L\.?)?\s*"
    r"(?P<amount>\d+(?:[.,]\d{1,2})?)\s*"
    r"(?P<cur2>\$|€|£|USD|EUR|LL|L\.?L\.?)?\s+"
    r"(?P<name>[A-Za-z\u0600-\u06FF].{0,80}?)\s*$",
    re.IGNORECASE,
)

# Table / multi-token: last token is amount(+currency), rest is name.
_PRICED_TRAILING_TOKEN_RE = re.compile(
    r"^\s*[-•*]?\s*(?P<name>[A-Za-z\u0600-\u06FF].{1,80}?)\s+"
    r"(?P<tail>(?:\$|€|£|USD|EUR|LL)?\s*\d+(?:[.,]\d{1,2})?\s*(?:\$|€|£|USD|EUR|LL)?)\s*$",
    re.IGNORECASE,
)

_TRAILING_AMOUNT_RE = re.compile(
    r"^(?P<cur>\$|€|£|USD|EUR|LL|L\.?L\.?)?\s*(?P<amount>\d+(?:[.,]\d{1,2})?)\s*(?P<cur2>\$|€|£|USD|EUR|LL|L\.?L\.?)?$",
    re.IGNORECASE,
)
_MARKUP_RE = re.compile(r"<[^>]+>")
_MD_NOISE_RE = re.compile(r"[*_`#]+")
# Last resort for selector files: require an explicit currency token next to the amount.
_FALLBACK_CUR_THEN_AMOUNT_RE = re.compile(
    r"^(?P<name>.+?)\s*(?::|=|-|–|—|\|)?\s*"
    r"(?P<cur>\$|€|£|USD|EUR|LL|L\.?L\.?)\s*(?P<amount>\d+(?:[.,]\d{1,2})?)\s*$",
    re.IGNORECASE,
)
_FALLBACK_AMOUNT_THEN_CUR_RE = re.compile(
    r"^(?P<name>.+?)\s*(?::|=|-|–|—|\|)?\s*"
    r"(?P<amount>\d+(?:[.,]\d{1,2})?)\s*(?P<cur>\$|€|£|USD|EUR|LL|L\.?L\.?)\s*$",
    re.IGNORECASE,
)


def _should_skip_non_price_line(line: str) -> bool:
    """Skip session/schedule rule lines, but keep lines that also contain a money amount."""
    if not _SKIP_LINE_RE.search(line):
        return False
    if re.search(
        r"(\$\s*\d|\d\s*\$|\bUSD\b\s*\d|\d\s*\bUSD\b|€\s*\d|\d\s*€|\bEUR\b\s*\d|\d\s*\bEUR\b)",
        line,
        re.IGNORECASE,
    ):
        return False
    return True


def _normalize_price_line(line: str) -> str:
    """Strip HTML/markdown noise without inventing tokens."""
    text = _MARKUP_RE.sub(" ", line or "")
    text = _MD_NOISE_RE.sub(" ", text)
    text = text.replace("\u00a0", " ").replace("\u2007", " ").replace("\u202f", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # Drop leading list markers / numbering prefixes.
    text = re.sub(r"^(?:[-•*]|\d+[.)])\s+", "", text)
    return text.strip()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    match = re.fullmatch(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:USD|EUR|LL|LBP)?", text, flags=re.IGNORECASE)
    if not match:
        # Allow plain "35" / "35.5" / "35 USD" already covered; also "USD 35"
        match = re.fullmatch(r"(?:USD|EUR|\$|€)?\s*(\d+(?:\.\d+)?)\s*(?:USD|EUR|\$|€)?", text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def _labels_from_name(name: str) -> LocalizedLabels:
    return LocalizedLabels(en=name, ar=name, fr=name)


def _item_id_from_name(name: str, *, fallback_prefix: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or f"{fallback_prefix}_{abs(hash(name)) % 10_000}"


def _currency_from_tokens(*tokens: str | None, default: str = "USD") -> str:
    for tok in tokens:
        if not tok:
            continue
        upper = tok.strip().upper().replace(".", "")
        if upper in {"$", "USD"}:
            return "USD"
        if upper in {"€", "EUR"}:
            return "EUR"
        if upper in {"£", "GBP"}:
            return "GBP"
        if upper in {"LL", "LBP"}:
            return "LBP"
    return default


def extract_price_rows_from_text(
    text: str,
    *,
    source: str,
    allow_space_amounts: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract proven name+amount rows from free text. Ambiguous lines returned separately (no invent).

    When ``allow_space_amounts`` is True (price selector files), also accept
    ``Name 40$`` / ``40$ Name`` / trailing-token amount forms. Without currency,
    space-separated amounts must be >= 15 to avoid importing session counts.
    """
    rows: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    if not text or not str(text).strip():
        return rows, ambiguous

    def _append(
        *,
        name: str,
        amount_raw: str,
        cur: str | None,
        cur2: str | None,
        line_no: int,
        require_currency_or_min: bool,
    ) -> bool:
        clean_name = name.strip().strip(".-–—|:")
        clean_name = clean_name.strip()
        amount = _as_float(amount_raw)
        if not clean_name or amount is None:
            return False
        if "." not in amount_raw and "," not in amount_raw and len(amount_raw) >= 7:
            return False
        has_currency = bool(cur or cur2)
        if require_currency_or_min and not has_currency and amount < 15:
            return False
        rows.append(
            {
                "id": _item_id_from_name(clean_name),
                "name": clean_name,
                "amount": amount,
                "currency": _currency_from_tokens(cur, cur2),
                "provenance": f"{source}:L{line_no}",
            }
        )
        return True

    for line_no, raw_line in enumerate(str(text).splitlines(), start=1):
        line = _normalize_price_line(raw_line)
        if not line or line.startswith("#") or set(line) <= {"-", "=", "_", "*"}:
            continue
        if _should_skip_non_price_line(line):
            continue
        matched = False
        match = _PRICED_LINE_RE.match(line)
        if match and _append(
            name=match.group("name") or "",
            amount_raw=str(match.group("amount") or ""),
            cur=match.group("cur"),
            cur2=match.group("cur2"),
            line_no=line_no,
            require_currency_or_min=False,
        ):
            matched = True
        elif allow_space_amounts:
            match = _PRICED_SPACE_EOL_RE.match(line)
            if match and _append(
                name=match.group("name") or "",
                amount_raw=str(match.group("amount") or ""),
                cur=match.group("cur"),
                cur2=match.group("cur2"),
                line_no=line_no,
                require_currency_or_min=True,
            ):
                matched = True
            else:
                match = _PRICED_LEADING_RE.match(line)
                if match and _append(
                    name=match.group("name") or "",
                    amount_raw=str(match.group("amount") or ""),
                    cur=match.group("cur"),
                    cur2=match.group("cur2"),
                    line_no=line_no,
                    require_currency_or_min=True,
                ):
                    matched = True
                else:
                    match = _PRICED_TRAILING_TOKEN_RE.match(line)
                    if match:
                        tail = _TRAILING_AMOUNT_RE.match((match.group("tail") or "").strip())
                        if tail and _append(
                            name=match.group("name") or "",
                            amount_raw=str(tail.group("amount") or ""),
                            cur=tail.group("cur"),
                            cur2=tail.group("cur2"),
                            line_no=line_no,
                            require_currency_or_min=True,
                        ):
                            matched = True
                    if not matched:
                        # Currency-required fallback for noisy selector lines (still no invent).
                        fb = _FALLBACK_CUR_THEN_AMOUNT_RE.match(line)
                        if fb and _append(
                            name=fb.group("name") or "",
                            amount_raw=str(fb.group("amount") or ""),
                            cur=fb.group("cur"),
                            cur2=None,
                            line_no=line_no,
                            require_currency_or_min=True,
                        ):
                            matched = True
                        else:
                            fb2 = _FALLBACK_AMOUNT_THEN_CUR_RE.match(line)
                            if fb2 and _append(
                                name=fb2.group("name") or "",
                                amount_raw=str(fb2.group("amount") or ""),
                                cur=None,
                                cur2=fb2.group("cur"),
                                line_no=line_no,
                                require_currency_or_min=True,
                            ):
                                matched = True
        if matched:
            continue
        if re.search(r"\d", line) and re.search(r"[A-Za-z\u0600-\u06FF]", line):
            ambiguous.append(
                {
                    "source": source,
                    "line_no": line_no,
                    "reason": "no_clear_name_amount_separator",
                    "line_len": len(line),
                }
            )
    return rows, ambiguous


def extract_price_rows_from_json_obj(
    obj: Any,
    *,
    source: str,
    allow_space_amounts: bool = False,
) -> list[dict[str, Any]]:
    """Best-effort extract of {id,name,amount,currency} from heterogeneous tenant JSON.

    Supports:
    - objects with name+amount keys (nested walk)
    - flat string→number maps
    - content-file shape ``{title, content}`` where ``content`` has priced lines
    Never invents amounts.
    """
    rows: list[dict[str, Any]] = []
    ambiguous_bucket: list[dict[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            # Content-file selector shape used by AI Setup price section.
            content = node.get("content")
            if isinstance(content, str) and content.strip():
                text_rows, ambiguous = extract_price_rows_from_text(
                    content,
                    source=f"{source}{path}/content",
                    allow_space_amounts=allow_space_amounts,
                )
                rows.extend(text_rows)
                ambiguous_bucket.extend(ambiguous)
            amount = None
            for key in _AMOUNT_KEYS:
                if key in node:
                    amount = _as_float(node.get(key))
                    if amount is not None:
                        break
            name = None
            for key in _NAME_KEYS:
                if key in node and str(node.get(key) or "").strip():
                    name = str(node.get(key)).strip()
                    break
            if amount is not None and name:
                item_id = str(node.get("id") or node.get("sku") or _item_id_from_name(name)).strip("_")
                rows.append(
                    {
                        "id": item_id or f"item_{len(rows)}",
                        "name": name,
                        "amount": amount,
                        "currency": str(node.get("currency") or "USD"),
                        "provenance": source if not path else f"{source}:{path}",
                    }
                )

            # Flat map: {"Arms": 35, "Legs": 50} — only when ALL values are numeric-ish and keys are names.
            if node and all(isinstance(k, str) for k in node.keys()):
                values = list(node.values())
                if (
                    values
                    and all(_as_float(v) is not None for v in values)
                    and all(
                        k.lower()
                        not in _AMOUNT_KEYS + _NAME_KEYS + ("id", "sku", "currency", "content", "tags", "language")
                        for k in node.keys()
                    )
                ):
                    # Avoid treating content-file metadata as a price map.
                    meta_keys = {"title", "audience", "priority", "created_at", "updated_at", "tags", "language"}
                    if not (meta_keys & {k.lower() for k in node.keys()}):
                        for key, value in node.items():
                            amount_v = _as_float(value)
                            if amount_v is None:
                                continue
                            rows.append(
                                {
                                    "id": _item_id_from_name(key),
                                    "name": key.strip(),
                                    "amount": amount_v,
                                    "currency": "USD",
                                    "provenance": f"{source}:map{path}",
                                }
                            )

            for key, value in node.items():
                if key == "content" and isinstance(value, str):
                    continue
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, f"{path}[{idx}]")

    walk(obj, "")
    # Attach ambiguous count on a side channel via provenance notes is not needed here;
    # callers that want archival use extract_with_ambiguous.
    _ = ambiguous_bucket

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        unique.append(row)
    return unique


def extract_price_rows_from_json_obj_with_ambiguous(
    obj: Any,
    *,
    source: str,
    allow_space_amounts: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Like extract_price_rows_from_json_obj but also returns ambiguous text-line ledger entries."""
    rows = extract_price_rows_from_json_obj(obj, source=source, allow_space_amounts=allow_space_amounts)
    ambiguous: list[dict[str, Any]] = []
    if isinstance(obj, dict) and isinstance(obj.get("content"), str):
        _, ambiguous = extract_price_rows_from_text(
            obj["content"],
            source=f"{source}/content",
            allow_space_amounts=allow_space_amounts,
        )
    return rows, ambiguous
