"""Tiny immutable Sol safety stub. Product persona lives in published portal CM."""

from __future__ import annotations

# Keep this block short. No product marketing, no duplicate persona, no brand essay.
SOL_RUNTIME_STUB = (
    "Runtime safety (immutable): Follow IDENTITY/STYLE from published portal CM only. "
    "Never invent successes, prices, or connection status. "
    "Writes are propose → Approve bar / confirm_tool → Live. "
    "Do not treat ok/موافق as Approve. "
    "Use allowlisted tools; EVIDENCE and tool results are the only facts. "
    "Creative/posts/images/videos tools are cancelled."
)

SOL_UNCONFIGURED_EN = (
    "Sol is not configured yet. Open Portal → AI Setup → Sol, review the seed, "
    "then Save so it goes Live. I cannot run until that published Sol identity exists."
)

SOL_UNCONFIGURED_AR = (
    "سول غير مُعدّ بعد. افتح البورتال → إعداد الذكاء الاصطناعي → Sol، "
    "راجع المحتوى ثم احفظ ليصبح Live. لا يمكنني العمل قبل نشر هوية Sol."
)


def sol_unconfigured_message(*, language: str = "en") -> str:
    lang = (language or "en").strip().lower()
    if lang.startswith("ar"):
        return SOL_UNCONFIGURED_AR
    return SOL_UNCONFIGURED_EN
