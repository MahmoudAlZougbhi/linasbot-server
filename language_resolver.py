"""
language_resolver.py

Language detection flow:

1) Arabic script -> "ar"
2) Franco-Arabic / Arabizi -> "franco" (bot responds in Arabic script)
3) English/French -> Use langdetect (trained model) as PRIMARY detection
   - Fallback to word list heuristics if langdetect unavailable or low confidence

Operational constraints
- Ignore "full name" messages in language detection (flag + heuristic)
- Avoid switching on low-signal inputs (very short messages)
- Arabizi digit scoring ignores digits used in TIME expressions (7pm, 19:30, 7h30, at 7, around 7, etc.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

try:
    from langdetect import detect, detect_langs, LangDetectException
except Exception:
    detect = None
    detect_langs = None
    LangDetectException = Exception


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
    # English pronouns/common words
    "i", "you", "he", "she", "we", "they", "it",
    "my", "your", "his", "her", "our", "their",
    "the", "a", "an", "and", "or", "but", "for", "with",
    "hello", "hi", "thanks", "thank", "please", "yes", "no",
    "would", "like", "want", "need", "book", "appointment", "help",
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


# ============================================================
# 7) State + resolver
# ============================================================

@dataclass
class LangState:
    lang_locked: str = "en"
    confidence: float = 0.0
    expecting_full_name: bool = False
    last_reasons: List[str] = field(default_factory=list)

class LanguageResolver:
    """
    Implemented rules:

    - Ignore full-name messages (flag or heuristic)
    - Arabic script => ar
    - Arabizi/Franco => ar (dominates everything including French)
    - Otherwise decide between fr/en:
        * If mixed fr+en: choose stronger evidence (NOT automatically French)
        * If still ambiguous: keep lang_locked
    - langdetect fallback used only if heuristic signals insufficient
    """

    # Switching guardrails
    MIN_ALPHA_FOR_SWITCH = 3  # Very low to allow short Franco phrases like "kifak"

    # Arabizi
    ARABIZI_THRESHOLD = 1  # Low: single Franco word like "kifak" = 2 points

    # Heuristic thresholds
    FR_EN_SCORE_MIN = 2  # Lowered: single French/English word = 2 points
    MIX_MIN_HITS = 1
    MIX_MARGIN = 2

    # French strength gating for mixed messages
    FRENCH_STRONG_HITS = 2

    # langdetect confidence threshold
    LANGDETECT_CONF_THRESHOLD = 0.70

    def __init__(self):
        self._cache: Dict[str, LangState] = {}

    def set_expecting_full_name(self, conversation_id: str, expecting: bool) -> None:
        state = self._cache.get(conversation_id) or LangState()
        state.expecting_full_name = expecting
        self._cache[conversation_id] = state

    def resolve(
        self,
        conversation_id: str,
        user_text: str,
        accept_language: Optional[str] = None,
        user_lang_override: Optional[str] = None,
    ) -> str:
        state = self._cache.get(conversation_id) or LangState(
            lang_locked=self._from_accept_language(accept_language) or "en"
        )

        raw = user_text or ""
        t = clean(raw)

        # explicit override
        if user_lang_override in {"ar", "en", "fr"}:
            state.lang_locked = user_lang_override
            state.confidence = 1.0
            state.last_reasons.append("user_override")
            self._cache[conversation_id] = state
            return state.lang_locked

        # ignore full names
        if state.expecting_full_name or looks_like_full_name(t):
            state.last_reasons.append("ignored_full_name")
            if state.expecting_full_name:
                state.expecting_full_name = False
            self._cache[conversation_id] = state
            return state.lang_locked


        # Arabic script dominates (check early, even for short messages)
        if ARABIC_RE.search(raw):
            state.lang_locked = "ar"
            state.confidence = 0.99
            state.last_reasons.append("arabic_script")
            self._cache[conversation_id] = state
            return "ar"

        # Franco/Arabizi dominates French and English
        arabizi_yes, arabizi_s = is_arabizi(raw, threshold=self.ARABIZI_THRESHOLD)
        if arabizi_yes:
            state.lang_locked = "ar"
            state.confidence = 0.90
            state.last_reasons.append(f"arabizi_score={arabizi_s}")
            self._cache[conversation_id] = state
            return "franco"  # Return "franco" to indicate Franco-Arabic was detected

        # Low-signal messages: keep previous language (after Arabic/Franco checks passed)
        # This prevents "ok", "yes", "manara" from switching language
        if alpha_len(t) < self.MIN_ALPHA_FOR_SWITCH:
            state.last_reasons.append("low_signal_keep")
            self._cache[conversation_id] = state
            return state.lang_locked

        # ============================================================
        # PRIMARY: Use langdetect for English/French detection
        # Trained models - much better than word lists
        # ============================================================
        detected = detect_en_fr(raw)
        if detected:
            lang, prob = detected
            if prob >= self.LANGDETECT_CONF_THRESHOLD:
                state.lang_locked = lang
                state.confidence = prob
                state.last_reasons.append(f"langdetect_primary={lang}:{prob:.2f}")
                self._cache[conversation_id] = state
                return lang

        # ============================================================
        # FALLBACK: Word list heuristics (if langdetect unavailable or low confidence)
        # ============================================================
        fr_score, fr_hits, fr_diac = french_features(raw)
        en_score, en_hits = english_features(raw)

        # French diacritics are a strong signal
        if fr_diac:
            state.lang_locked = "fr"
            state.confidence = 0.85
            state.last_reasons.append(f"french_diacritics(hits={fr_hits})")
            self._cache[conversation_id] = state
            return "fr"

        # Use word list scores as fallback
        if fr_score >= self.FR_EN_SCORE_MIN and fr_score > en_score:
            state.lang_locked = "fr"
            state.confidence = min(0.80, 0.50 + fr_score / 20)
            state.last_reasons.append(f"fallback_fr_score={fr_score}(hits={fr_hits})")
            self._cache[conversation_id] = state
            return "fr"

        if en_score >= self.FR_EN_SCORE_MIN and en_score > fr_score:
            state.lang_locked = "en"
            state.confidence = min(0.80, 0.50 + en_score / 20)
            state.last_reasons.append(f"fallback_en_score={en_score}(hits={en_hits})")
            self._cache[conversation_id] = state
            return "en"

        # Default: keep locked
        state.last_reasons.append("keep_locked")
        self._cache[conversation_id] = state
        return state.lang_locked

    def _from_accept_language(self, header: Optional[str]) -> Optional[str]:
        if not header:
            return None
        token = header.split(",")[0].strip()
        if not token:
            return None
        base = token.split("-")[0].lower()
        return base if base in {"ar", "en", "fr"} else None


# ============================================================
# 8) Prompt injection helper
# ============================================================

def system_language_instruction(lang: str) -> str:
    if lang == "ar":
        return (
            "Respond in Arabic using Arabic script. "
            "If the user writes Franco-Arabic/Arabizi, still respond in Arabic script. "
            "Keep code, product names, and identifiers in Latin characters when needed."
        )
    if lang == "fr":
        return (
            "Réponds en français. "
            "Garde le code, les noms de produits, et les identifiants en alphabet latin si nécessaire."
        )
    return (
        "Respond in English. "
        "Keep code, product names, and identifiers in Latin characters when needed."
    )
