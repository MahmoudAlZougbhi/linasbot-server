"""Shared output-formatting guidance for Linas AI replies (guest, owner, customer).

Keep this small and reusable. Product scope / facts stay in each surface's own prompt;
this module only covers how replies should look on the page or in a comment/DM.
"""

from __future__ import annotations

# Injected into guest, owner copilot, CM customer answers, and Meta comment/DM paths.
RESPONSE_FORMATTING_RULES = (
    "OUTPUT FORMAT (ar/en/fr — same structure rules in every language):\n"
    "- Never write one dense wall of text or stack sentences randomly on top of each other.\n"
    "- Structure longer answers as: a short clear intro, then numbered 1 / 2 / 3 "
    "(or clean bullets) when listing features, steps, options, or benefits.\n"
    "- Keep paragraphs short (about 1–3 sentences). Use a blank line between sections "
    "when the reply has more than one part.\n"
    "- When mixing Arabic or French with English product names "
    "(Instagram, Facebook, AI Setup, Content Manager, System Copilot, Linas AI), "
    "keep each English name intact and place it cleanly — never broken, jammed, "
    "or scrambled mid-line.\n"
    "- Make replies scannable and easy to read. Prefer clarity over length.\n"
    "- Short public comments or brief DMs: stay brief, but if you list 2+ points still use "
    "a tiny intro plus numbered/bulleted lines — never a wall of text."
)
