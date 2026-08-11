"""
language_resolver_text.py

Text helpers for language_resolver: cleaning, tokenization, time masking,
and full-name heuristics. (LOC split from language_resolver.)
"""

from __future__ import annotations

import re
from typing import List


# ============================================================
# 1) Helpers: cleaning, tokenization, counts
# ============================================================

ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
CODEBLOCK_RE = re.compile(r"```.*?```", re.DOTALL)

def clean(text: str) -> str:
    """Light normalization; keeps digits (needed for Arabizi)."""
    text = CODEBLOCK_RE.sub(" ", text or "")
    text = URL_RE.sub(" ", text)
    text = re.sub(r"\S+@\S+", " ", text)  # emails
    text = re.sub(r"\s+", " ", text).strip()
    return text

def alpha_len(text: str) -> int:
    """Count alphabetic chars across scripts."""
    return sum(ch.isalpha() for ch in text)

def tokenize(text: str) -> List[str]:
    """Tokenize Latin/accents/digits/apostrophes; keeps digits for Arabizi."""
    return re.findall(r"[a-zA-Z0-9\u00C0-\u00FF']+", (text or "").lower())


# ============================================================
# 2) Time masking (prevents false Arabizi digit scoring)
# ============================================================

TIME_PATTERNS = [
    # 7pm, 7 pm, 7p.m., 7 p.m., 11am
    r"\b([01]?\d)\s*(a\.?m\.?|p\.?m\.?)\b",

    # 7:15, 07:15, 19:30 (+ optional am/pm)
    r"\b([01]?\d|2[0-3])\s*:\s*([0-5]\d)\s*(a\.?m\.?|p\.?m\.?)?\b",

    # French-style: 7h, 7 h, 7h30, 7 h 30, 19h, 19h30
    r"\b([01]?\d|2[0-3])\s*h\s*([0-5]\d)?\b",

    # "at 7", "at 7 pm", "around 7", "by 7", "from 7", "till 7", etc.
    r"\b(?:at|around|about|by|before|after|from|till|until|to)\s*([01]?\d|2[0-3])\b",

    # French: "à 7", "vers 7", "avant 7", "après 7", "de 7", "jusqu'à 7"
    r"\b(?:à|vers|environ|avant|après|de|depuis|jusqu(?:'|'|`)à)\s*([01]?\d|2[0-3])\b",
]

TIME_RE = re.compile("|".join(f"(?:{p})" for p in TIME_PATTERNS), re.IGNORECASE)

def mask_times(text: str) -> str:
    """
    Replace time-like expressions with <TIME> so they don't trigger Arabizi digit scoring.
    """
    return TIME_RE.sub(" <TIME> ", text)


# ============================================================
# 3) Full-name ignoring (flag + heuristic)
# ============================================================

FULL_NAME_RE = re.compile(r"^[A-Za-z\u00C0-\u00FF]+(?:[ -][A-Za-z\u00C0-\u00FF]+){1,4}$")

# Words that should NOT be treated as names (Franco + common pronouns/articles/verbs)
NAME_EXCLUSIONS = {
    # Franco-Arabic
    "ana", "isme", "ismi", "esme", "esmi",  # "I" / "my name"
    "shab", "chab", "sabieh", "sabiye",  # gender words
    "bade", "badde", "badi",  # "I want"
    "shu", "shou", "chou",  # "what"
    "kifak", "kifik",  # "how are you"
    "wein", "wen", "fein",  # "where"
    "la2", "eh", "aiwa",  # yes/no
    # French pronouns/articles/common words (indicate a sentence, not a name)
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "on",
    "un", "une", "le", "la", "les", "des", "du", "de", "au", "aux",
    "merci", "bonjour", "salut", "oui", "non", "pour", "votre", "avec",
    "comment", "beaucoup", "bien", "très", "aide", "rendez",
    # French verbs/phrases that indicate "my name is" patterns (NOT names)
    "mappelle", "m'appelle", "appelle", "suis", "moi", "c'est",
    # English pronouns/common words
    "i", "you", "he", "she", "we", "they", "it",
    "my", "your", "his", "her", "our", "their",
    "the", "a", "an", "and", "or", "but", "for", "with",
    "hello", "hi", "thanks", "thank", "please", "yes", "no",
    "would", "like", "want", "need", "book", "appointment", "help",
    # English name introduction phrases (NOT names)
    "name", "is", "am", "im", "call", "my names", "name's"
}

def looks_like_full_name(text: str) -> bool:
    """
    Heuristic: 2–5 words, letters only (Latin + accents), space/hyphen allowed.
    No digits, no punctuation.
    Excludes common Franco-Arabic phrases that look like names.
    """
    t = clean(text)
    if not t or len(t) > 70:
        return False
    if any(ch.isdigit() for ch in t):
        return False
    if re.search(r"[?.!,;:/\\(){}[\]@#%&*_+=]", t):
        return False

    # Check if any word is a known non-name word (Franco, pronouns, articles)
    words = t.lower().split()
    if any(word in NAME_EXCLUSIONS for word in words):
        return False

    return bool(FULL_NAME_RE.match(t))
