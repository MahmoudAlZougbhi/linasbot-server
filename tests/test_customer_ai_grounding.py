"""Deterministic grounding: money, hours, phones, urls, stock, booking + one repair loop."""

from __future__ import annotations

import pytest

from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.grounding.facts import (
    evidence_supports_text,
    ungrounded_amounts,
    ungrounded_claims,
)


def _bundle(*texts: str) -> EvidenceBundle:
    return EvidenceBundle(
        outcome="found",
        items=[
            EvidenceItem(
                evidence_id=f"knowledge:e{index}",
                source_family="knowledge",
                source_id=f"e{index}",
                title=f"Doc {index}",
                text=text,
            )
            for index, text in enumerate(texts)
        ],
    )


def _kinds(reasons: list[str]) -> set[str]:
    return {reason.split(":", 1)[0] for reason in reasons}


def test_money_checks_are_kept() -> None:
    bundle = _bundle("Hair Removal\n99.0 USD / session")
    assert ungrounded_amounts("Hair removal is 250 USD", bundle) == ["250|usd"]
    assert ungrounded_amounts("Hair removal is 99.0 USD", bundle) == []
    assert evidence_supports_text("Hair removal is 99.0 USD", bundle) is True
    assert _kinds(ungrounded_claims("It costs $250", bundle)) == {"amount"}
    # Same amount written differently is still the same amount.
    assert ungrounded_claims("It is 99 USD", bundle) == []


def test_invented_opening_hours_are_ungrounded() -> None:
    bundle = _bundle("Beirut branch\nmonday 09:00 - 18:00\ntuesday 09:00 - 18:00")
    assert ungrounded_claims("We are open until 18:00 on monday", bundle) == []
    invented_time = ungrounded_claims("We are open until 23:00 on monday", bundle)
    assert _kinds(invented_time) == {"hours"}
    invented_day = ungrounded_claims("We are open 09:00 - 18:00 on sunday", bundle)
    assert any(reason.startswith("hours:day:sunday") for reason in invented_day)


def test_day_names_are_compared_across_languages() -> None:
    bundle = _bundle("Beirut branch\nmonday 09:00 - 18:00")
    # Arabic reply against English evidence is the same day, not an invented one.
    assert ungrounded_claims("يوم الاثنين مفتوحين من 09:00 لـ 18:00", bundle) == []
    assert "hours:day:sunday" in ungrounded_claims("مفتوحين يوم الاحد من 09:00 لـ 18:00", bundle)


def test_clock_times_are_not_read_as_phone_numbers() -> None:
    bundle = _bundle("Branch\nmonday 09:00 - 18:00\ntuesday 10:00 - 20:00")
    assert ungrounded_claims("Monday 09:00 - 18:00 and tuesday 10:00 - 20:00", bundle) == []


def test_open_claim_without_any_hours_evidence_fails_closed() -> None:
    bundle = _bundle("Hair Removal\n99.0 USD / session")
    assert "hours:no_hours_evidence" in ungrounded_claims("We are open every day", bundle)


def test_twelve_hour_and_twenty_four_hour_forms_match() -> None:
    bundle = _bundle("Branch\nsaturday 10:00 - 17:00")
    assert ungrounded_claims("On saturday we close at 5pm", bundle) == []
    assert _kinds(ungrounded_claims("On saturday we close at 8pm", bundle)) == {"hours"}


def test_invented_phone_and_url_are_ungrounded() -> None:
    bundle = _bundle("Contact\nCall 01 345 678\nBook at https://Example.com/book")
    assert ungrounded_claims("Call 01 345 678 or visit https://example.com/book", bundle) == []
    assert _kinds(ungrounded_claims("Call 03 999 111", bundle)) == {"phone"}
    assert _kinds(ungrounded_claims("Visit https://evil.example.org/pay", bundle)) == {"url"}
    # International prefix of the same number is the same number.
    assert ungrounded_claims("Call +961 1 345 678", bundle) == []


def test_stock_claims_need_stock_evidence() -> None:
    silent = _bundle("Vitamin C Serum\n30 USD")
    assert _kinds(ungrounded_claims("The serum is in stock", silent)) == {"stock"}
    assert _kinds(ungrounded_claims("It is available now", silent)) == {"stock"}
    stocked = _bundle("Vitamin C Serum\n30 USD\nstock: 4 units available")
    assert ungrounded_claims("The serum is in stock", stocked) == []


def test_booking_success_needs_a_receipt() -> None:
    bundle = _bundle("Laser session\n99.0 USD")
    assert _kinds(ungrounded_claims("I booked your session", bundle)) == {"booking"}
    assert _kinds(ungrounded_claims("I confirmed your appointment", bundle)) == {"booking"}
    failed = ungrounded_claims("I booked your session", bundle, receipts=["booking:failed:upstream_down"])
    assert _kinds(failed) == {"booking"}
    ok = ungrounded_claims("I booked your session", bundle, receipts=["booking:confirmed:bk_9"])
    assert ok == []


def test_empty_reply_and_empty_evidence_fail_closed() -> None:
    bundle = _bundle("Laser session\n99.0 USD")
    assert ungrounded_claims("", bundle) == ["reply:empty"]
    assert ungrounded_claims("   ", bundle) == ["reply:empty"]
    assert ungrounded_claims("We open at 10:00", EvidenceBundle()) == ["evidence:empty"]
    assert evidence_supports_text("We open at 10:00", EvidenceBundle()) is False


def test_multiple_ungrounded_kinds_are_all_reported() -> None:
    bundle = _bundle("Laser session\n99.0 USD")
    reasons = ungrounded_claims(
        "Laser is 250 USD, we are open until 22:00, call 03 111 222 and visit https://nope.example",
        bundle,
    )
    assert _kinds(reasons) == {"amount", "hours", "phone", "url"}
    assert len(reasons) == len(set(reasons))


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


def _turn() -> CustomerTurn:
    return CustomerTurn(tenant_id="t1", conversation_id="c1", channel="instagram_dm", event_ids=["ev1"])


def _plan() -> PlannerPlan:
    return PlannerPlan(tasks=[PlannerTask(id="t1", type="information", source_families=["services"])])


@pytest.fixture
def _no_provider_expense(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.membership.provider_expense.record_pending_provider",
        lambda **_kwargs: None,
    )


async def _run_generate(monkeypatch: pytest.MonkeyPatch, replies: list[str], bundle: EvidenceBundle):
    from services.customer_ai.generate.reply import generate_grounded_reply

    calls: list[str] = []

    async def fake_completion(*, model: str, messages: list[dict], max_tokens: int = 0, **_kwargs):
        calls.append(str(messages[-1]["content"]))
        index = min(len(calls) - 1, len(replies) - 1)
        return _FakeResponse(replies[index])

    monkeypatch.setattr("services.llm_core_service.create_chat_completion", fake_completion)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    envelope = await generate_grounded_reply(
        turn=_turn(),
        message="how much is laser?",
        plan=_plan(),
        bundle=bundle,
        identity=None,
        destination="dm",
    )
    return envelope, calls


@pytest.mark.asyncio
async def test_repair_loop_retries_once_then_accepts(
    monkeypatch: pytest.MonkeyPatch, _no_provider_expense: None
) -> None:
    bundle = _bundle("Laser session\n99.0 USD / session")
    envelope, calls = await _run_generate(
        monkeypatch,
        ["Laser is 250 USD", "Laser is 99.0 USD per session"],
        bundle,
    )
    assert len(calls) == 2
    assert "GROUNDING_REJECTED" in calls[1]
    assert "250|usd" in calls[1]
    assert envelope is not None
    assert envelope.decision == "reply"
    assert envelope.messages[0].text == "Laser is 99.0 USD per session"
    assert envelope.used_evidence_ids == ["knowledge:e0"]


@pytest.mark.asyncio
async def test_repair_loop_fails_closed_after_one_retry(
    monkeypatch: pytest.MonkeyPatch, _no_provider_expense: None
) -> None:
    bundle = _bundle("Laser session\n99.0 USD / session")
    envelope, calls = await _run_generate(monkeypatch, ["Laser is 250 USD"], bundle)
    assert len(calls) == DEFAULT_BUDGETS.repair_attempts + 1 == 2
    assert envelope is not None
    assert envelope.decision == "clarify"
    assert envelope.messages == []


@pytest.mark.asyncio
async def test_grounded_first_reply_does_not_repair(
    monkeypatch: pytest.MonkeyPatch, _no_provider_expense: None
) -> None:
    bundle = _bundle("Laser session\n99.0 USD / session")
    envelope, calls = await _run_generate(monkeypatch, ["Laser is 99.0 USD per session"], bundle)
    assert len(calls) == 1
    assert envelope is not None and envelope.decision == "reply"


@pytest.mark.asyncio
async def test_empty_evidence_never_generates_a_factual_reply(
    monkeypatch: pytest.MonkeyPatch, _no_provider_expense: None
) -> None:
    envelope, calls = await _run_generate(monkeypatch, ["Laser is 99.0 USD"], EvidenceBundle())
    assert calls == []
    assert envelope is not None
    assert envelope.decision == "clarify"
    assert envelope.messages == []
    assert envelope.used_evidence_ids == []


@pytest.mark.asyncio
async def test_missing_openai_is_not_a_fake_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.generate.reply import generate_grounded_reply

    monkeypatch.setenv("OPENAI_API_KEY", "")
    envelope = await generate_grounded_reply(
        turn=_turn(),
        message="how much is laser?",
        plan=_plan(),
        bundle=_bundle("Laser session\n99.0 USD"),
        identity=None,
        destination="dm",
    )
    assert envelope is None


def test_system_prompt_and_rules_forbid_invention() -> None:
    from services.customer_ai.compose.blocks import RULES_BLOCK, compose_evidence_context, system_prompt

    prompt = system_prompt()
    assert "ONLY" in prompt
    for forbidden in ("prices", "opening hours", "phone numbers", "stock", "booking"):
        assert forbidden in prompt
    context = compose_evidence_context(identity=None, plan=_plan(), bundle=_bundle("Laser\n99.0 USD"))
    assert RULES_BLOCK in context
    assert "EVIDENCE" in context
