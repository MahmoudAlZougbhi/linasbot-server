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

Helpers/signals: language_resolver_text, language_resolver_signals (LOC split).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, List

# Public re-exports (keep `from language_resolver import ...` working)
from language_resolver_text import (  # noqa: F401
    ARABIC_RE,
    URL_RE,
    CODEBLOCK_RE,
    FULL_NAME_RE,
    NAME_EXCLUSIONS,
    TIME_PATTERNS,
    TIME_RE,
    alpha_len,
    clean,
    looks_like_full_name,
    mask_times,
    tokenize,
)
from language_resolver_signals import (  # noqa: F401
    ARABIZI_DIGITS_RE,
    ARABIZI_WORDS,
    ENGLISH_MARKERS,
    FRENCH_DIACRITICS_RE,
    FRENCH_MARKERS,
    arabizi_score,
    detect_en_fr,
    english_features,
    french_features,
    is_arabizi,
)


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

        # ============================================================
        # Franco/Arabizi detection with smart override
        # STRONG signals (digits or high score) → Franco wins immediately
        # WEAK signals (single word match) → Check langdetect first
        # ============================================================
        arabizi_yes, arabizi_s = is_arabizi(raw, threshold=self.ARABIZI_THRESHOLD)
        has_arabizi_digits = bool(ARABIZI_DIGITS_RE.search(mask_times(clean(raw).lower())))

        # STRONG Franco signal: digits present OR high score (>=4 = at least 2 word matches)
        if arabizi_yes and (has_arabizi_digits or arabizi_s >= 4):
            state.lang_locked = "ar"
            state.confidence = 0.90
            state.last_reasons.append(f"arabizi_strong={arabizi_s}(digits={has_arabizi_digits})")
            self._cache[conversation_id] = state
            return "franco"

        # WEAK Franco signal: check langdetect first to avoid false positives
        # e.g., French "la machine" matching Franco "la" (no)
        if arabizi_yes and arabizi_s < 4:
            detected = detect_en_fr(raw)
            if detected:
                lang, prob = detected
                # If langdetect is confident it's French/English, trust it over weak Franco
                if prob >= 0.80:
                    state.lang_locked = lang
                    state.confidence = prob
                    state.last_reasons.append(f"langdetect_over_weak_franco={lang}:{prob:.2f}(arabizi_s={arabizi_s})")
                    self._cache[conversation_id] = state
                    return lang
            # langdetect not confident, fall back to Franco
            state.lang_locked = "ar"
            state.confidence = 0.70
            state.last_reasons.append(f"arabizi_weak={arabizi_s}")
            self._cache[conversation_id] = state
            return "franco"

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
                # Single short word (e.g. "laser", "hair") + user was in Arabic mode:
                # Don't switch to English - user likely continuing in same language
                words = raw.split()
                prev_ar = state.lang_locked == "ar"
                if (
                    lang == "en"
                    and len(words) <= 1
                    and alpha_len(t) <= 8
                    and prev_ar
                ):
                    state.last_reasons.append(
                        f"single_word_en_keep_ar(len={alpha_len(t)},prev={state.lang_locked})"
                    )
                    self._cache[conversation_id] = state
                    return state.lang_locked
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
