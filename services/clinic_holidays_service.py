"""
Branch holiday / closure calendar for AI context (Settings → Clinic).
Used to block booking on specific dates per branch and to drive seasonal greetings.
"""

from __future__ import annotations

import datetime
from typing import Any

import config
from services.settings_service import settings_service


def _parse_iso_date(s: str | None) -> datetime.date | None:
    if not s or not str(s).strip():
        return None
    try:
        return datetime.date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        return None


def get_branch_holidays_config() -> list[dict[str, Any]]:
    clinic = settings_service.settings.get("clinic") or {}
    raw = clinic.get("branchHolidays")
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def build_clinic_holiday_block_for_prompt(user_id: str, current_local_time: datetime.datetime) -> str:
    """
    Append to system prompt: configured closures + rules for booking + greetings.
    """
    entries = get_branch_holidays_config()
    if not entries:
        return ""

    branch_id: int | None = None
    try:
        st = config.user_booking_state.get(user_id) or {}
        if st.get("branch_id") is not None:
            branch_id = int(st.get("branch_id") or 0)
    except (TypeError, ValueError):
        branch_id = None
    if branch_id is None:
        try:
            db = getattr(config, "DEFAULT_BRANCH_ID", None)
            branch_id = int(db) if db is not None else None
        except (TypeError, ValueError):
            branch_id = None

    today = current_local_time.date()
    lines: list[str] = [
        "**🎉 BRANCH HOLIDAYS / CLOSURES (from dashboard Settings — MANDATORY):**\n",
        f"- **Context branch_id for this user** (booking context): {branch_id if branch_id is not None else 'unknown — infer from conversation or tools'}\n",
        "- **Matching rule**: A row applies to a booking at branch B if `branchId` is empty/null **or** `branchId == B` (Beirut=1, Antelias=2 unless your CRM differs).\n",
        "- **When the user asks for an appointment ON a calendar day that falls inside [startDate..endDate] for an applicable row**:\n",
        "  - If `blockBooking` is true: **do NOT** run `submit_booking_intent` / `create_appointment` / confirm a slot for **that day** for that branch. Say the branch is closed that day because of that occasion (use **labelAr** / **labelEn**).\n",
        "  - **Same `bot_reply` (one message) — combine all of:** (1) a short warm line using **greetingAr** (Arabic) or **greetingEn** (English) from the row; (2) clearly that **we are closed / no appointments that day** for this reason; (3) ask which **other day** they prefer **after** the holiday range, or suggest 1–2 example dates after `endDate`. Keep it short.\n",
        "  - Do not pretend the booking was created for the closed day.\n",
        "- **If today** is inside the holiday range for their branch: you may start with one seasonal line (from greetings) **when** they are asking to book/reschedule — not in every unrelated message.\n",
        "- **If they only mention the occasion** without a date: reply with the greeting + ask what day they want; when they name a date inside a closed range, apply the rules above.\n",
        "**Configured rows (ranges inclusive; branch empty = all branches):**\n",
    ]

    for i, e in enumerate(entries, 1):
        sd = _parse_iso_date(e.get("startDate"))
        ed = _parse_iso_date(e.get("endDate")) or sd
        if sd and ed and ed < sd:
            sd, ed = ed, sd
        block = bool(e.get("blockBooking", True))
        label_ar = str(e.get("labelAr") or "").strip() or "—"
        label_en = str(e.get("labelEn") or "").strip() or "—"
        gr_ar = str(e.get("greetingAr") or "").strip() or "—"
        gr_en = str(e.get("greetingEn") or "").strip() or "—"
        br = e.get("branchId")
        br_lbl = "all branches" if br is None or br == "" else f"branch_id={br}"
        dr = f"{sd.isoformat() if sd else '?'} .. {ed.isoformat() if ed else '?'}"
        active = ""
        if sd and ed:
            try:
                if sd <= today <= ed:
                    active = " [TODAY IN THIS RANGE]"
            except Exception:
                pass
        lines.append(
            f"  {i}. [{br_lbl}] {dr}{active} | {label_ar} / {label_en} | "
            f"blockBooking={block} | greeting AR: «{gr_ar}» | EN: «{gr_en}»\n"
        )

    return "\n" + "".join(lines)
