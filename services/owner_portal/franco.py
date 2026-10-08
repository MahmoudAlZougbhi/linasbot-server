"""Franco Q&A text. Natural Arabizi first, letter map only as a fallback."""

from __future__ import annotations

import re

_LETTERS = {
    "ا": "a",
    "أ": "a",
    "إ": "i",
    "آ": "aa",
    "ب": "b",
    "ت": "t",
    "ث": "th",
    "ج": "j",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "dh",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "و": "w",
    "ي": "y",
    "ى": "a",
    "ة": "a",
    "ء": "",
    "ئ": "y",
    "ؤ": "w",
    "ـ": "",
}


def _arabic_char(char: str) -> bool:
    return "\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f"


def has_arabic_script(text: str) -> bool:
    return any(_arabic_char(char) for char in text or "")


def verbatim_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+|\d{2,}", text or "")


def keep_verbatim(source: str, translated: str) -> str:
    """Keep the source when a translation drops a name, code, number, or label."""
    cleaned = (translated or "").strip()
    original = (source or "").strip()
    if not cleaned:
        return original
    if any(token not in cleaned for token in verbatim_tokens(original)):
        return original
    return cleaned


async def franco_pair(question: str, answer: str) -> tuple[str, str]:
    """Natural Latin Arabizi. Falls back to the letter map after one retry."""
    from services.owner_portal.protected_text import mask_tokens, restore_tokens

    masked_question, question_tokens = mask_tokens(question)
    masked_answer, answer_tokens = mask_tokens(answer)
    locked = verbatim_tokens(f"{question}\n{answer}")
    for _attempt in range(2):
        rendered = await _ask_franco(masked_question, masked_answer)
        parts = [part.strip() for part in (rendered or "").split("\n---\n", 1)]
        if len(parts) != 2:
            continue
        restored = [restore_tokens(parts[0], question_tokens), restore_tokens(parts[1], answer_tokens)]
        combined = " ".join(restored)
        if has_arabic_script(combined):
            continue
        if any(token not in combined for token in locked):
            continue
        if not re.search(r"[aeiou]", combined, re.I):
            continue
        return restored[0], restored[1]
    return to_franco(question), to_franco(answer)


async def _ask_franco(question: str, answer: str) -> str:
    from services.brain.llm_core_service import create_chat_completion
    from services.owner_copilot.flags import owner_model_name

    response = await create_chat_completion(
        model=owner_model_name(),
        messages=[
            {
                "role": "system",
                "content": (
                    "Rewrite the question and answer as natural Lebanese Arabizi in Latin letters. "
                    "Keep product names, codes, numbers, and a leading QA- label verbatim. "
                    "Reply with the question, a line containing only ---, then the answer."
                ),
            },
            {"role": "user", "content": f"{question}\n---\n{answer}"},
        ],
        max_tokens=400,
        reasoning_effort="low",
    )
    return str(response.choices[0].message.content or "")


def to_franco(text: str) -> str:
    """Latin-script Arabizi. Arabic letters never remain in the result."""
    pieces: list[str] = []
    for char in text or "":
        if char in _LETTERS:
            pieces.append(_LETTERS[char])
        elif _arabic_char(char):
            continue
        else:
            pieces.append(char)
    return " ".join("".join(pieces).split())
