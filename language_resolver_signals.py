"""
language_resolver_signals.py

Language signal scoring for language_resolver: Arabizi/Franco, French/English
heuristics, and langdetect EN/FR. (LOC split from language_resolver.)
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from language_resolver_text import alpha_len, clean, mask_times, tokenize

try:
    from langdetect import detect, detect_langs, LangDetectException
except Exception:
    detect = None
    detect_langs = None
    LangDetectException = Exception


# ============================================================
# 4) Arabizi / Franco-Arabic detection (dominates everything)
# ============================================================

ARABIZI_DIGITS_RE = re.compile(r"[2356789]")  # phoneme digits

ARABIZI_WORDS = {
    # Greetings
    "kifak", "kifik", "kifkon", "kif",
    "marhaba", "ahla", "ahlan", "ahleen",
    "sabah", "masa", "saba7", "masa2",

    # Common verbs/phrases
    "bade", "badde", "bde", "badi", "baddi", "bdi",
    "a3mel", "a3mil", "3amel", "3amil",  # "to do/make"
    "rouh", "ruh", "roh",  # "go"
    "ta3a", "ta3i", "ta3o",  # "come"
    "sheel", "shil", "shel",  # "remove"

    # Questions
    "le", "leh", "lesh", "leish", "ليش",
    "sho", "shu", "shou", "chou",
    "wen", "wein", "wayn", "fein", "fain",
    "aya", "ayya", "ayya",
    "adesh", "addesh", "2adesh", "2addesh", "adde", "2adde",

    # Gender words (CRITICAL for gender detection)
    "shab", "chab", "shabb",  # male
    "sabieh", "sabiye", "sabiyeh", "benet", "bint",  # female
    "zakar", "ontha",  # formal male/female

    # Name-related
    "esme", "esmi", "isme", "ismi", "ana",

    # Prices/services
    "se3er", "s3r", "as3ar", "asaar", "si3r",
    "jalse", "jalseh", "jalset",
    "makana", "makane", "makanet",
    "washem", "washmet", "washme",
    "tebyeed", "tebyid",

    # Common words
    "bi", "fi", "fih", "feeh",
    "ma", "msh", "mesh", "mish",
    "hek", "heik", "hayk", "heke",
    "tab", "tayeb", "tayyeb",
    "ktir", "kteer", "ktr", "ketir",
    "waja3", "wj3", "btwaje3",
    "hbb", "7bb", "7abibi", "habibi", "habibti",

    # Time/scheduling
    "bukra", "bokra", "ba3d", "ba3den",
    "lyom", "elyom", "alyom",
    "kel", "kil",  # "every"

    # Confirmations
    "la2", "laa", "la", "eh", "eih", "ah", "aiwa",
    "yalla", "yas", "tamam", "tammam",
    "mn7", "mne7", "mnee7", "mnih",

    # Other common
    "shukran", "thanks",  # NOTE: "merci" removed - it's French, not Franco
    "3am", "3amma",
    "arkhas", "ar5as",
    "ghale", "8ale", "8ali", "ghali",
    "w", "wel", "wil",  # "and"
}

def arabizi_score(text: str) -> int:
    """
    Score-based Arabizi detection.
    Signals:
      - phoneme digits (excluding time-like digits)
      - lexicon hits
      - digit+vowel co-occurrence (excluding time-like digits)
    """
    raw = clean(text).lower()
    raw_no_time = mask_times(raw)
    toks = tokenize(raw)

    score = 0

    # Strong signal: phoneme digits, but ignore time expressions
    if ARABIZI_DIGITS_RE.search(raw_no_time):
        score += 3

    # Lexicon hits
    hits = len(set(toks) & ARABIZI_WORDS)
    score += min(12, hits * 2)

    # Bonus: digits + vowels pattern, but ignore time expressions
    if re.search(r"\d", raw_no_time) and re.search(r"[aeiou]", raw_no_time):
        score += 2

    return score

def is_arabizi(text: str, threshold: int) -> Tuple[bool, int]:
    s = arabizi_score(text)
    return (s >= threshold), s


# ============================================================
# 5) French/English scoring (French is NOT auto-dominant)
# ============================================================

FRENCH_MARKERS = {
    # NOTE: "bonjour" excluded - too common, shouldn't switch language alone
    "salut", "merci", "svp", "stp", "oui", "non",
    "je", "j", "tu", "vous", "il", "elle", "on", "nous", "ils", "elles",
    "mon", "ma", "mes", "ton", "ta", "tes", "votre", "vos",
    "de", "des", "du", "au", "aux", "dans", "avec", "sans", "pour", "sur",
    "et", "mais", "donc", "parce", "que", "quoi", "comment", "pourquoi",
    "rdv", "rendezvous", "rendez-vous",
}
FRENCH_DIACRITICS_RE = re.compile(r"[àâäéèêëïîôùûüÿçœæÀÂÄÉÈÊËÏÎÔÙÛÜŸÇŒÆ]", re.IGNORECASE)

ENGLISH_MARKERS = {
    "hi", "hello", "thanks", "thank", "please", "yes", "no",
    "i", "you", "we", "they", "he", "she",
    "my", "your", "our", "their",
    "the", "a", "an", "and", "but", "because",
    "appointment", "schedule", "price", "cost", "laser",
    "want", "need", "can", "would", "like",
    "what", "when", "where", "how", "why",
}

def _marker_hits(tokens: List[str], marker_set: set) -> int:
    return len(set(tokens) & marker_set)

def french_features(text: str) -> Tuple[int, int, bool]:
    raw = clean(text)
    toks = tokenize(raw)
    hits = _marker_hits(toks, FRENCH_MARKERS)
    has_diacritics = bool(FRENCH_DIACRITICS_RE.search(raw))

    score = 0
    if has_diacritics:
        score += 4
    score += min(10, hits * 2)
    if re.search(r"\b(j'|l'|d'|qu')", raw.lower()):
        score += 2
    return score, hits, has_diacritics

def english_features(text: str) -> Tuple[int, int]:
    raw = clean(text)
    toks = tokenize(raw)
    hits = _marker_hits(toks, ENGLISH_MARKERS)
    score = min(10, hits * 2)
    return score, hits


# ============================================================
# 6) Language detection for English/French (langdetect)
# ============================================================

def detect_en_fr(text: str) -> Optional[Tuple[str, float]]:
    """
    Returns ("en"|"fr", probability) or None.
    Uses langdetect for detection.
    Only used after Arabic/Franco checks pass.
    """
    raw = clean(text)
    if alpha_len(raw) < 10:  # Need some text to detect
        return None

    if detect and detect_langs:
        try:
            results = detect_langs(raw)
            for result in results:
                lang = str(result.lang).lower()
                prob = float(result.prob)
                if lang == "fr":
                    return "fr", prob
                if lang == "en":
                    return "en", prob
        except LangDetectException:
            pass

    return None
