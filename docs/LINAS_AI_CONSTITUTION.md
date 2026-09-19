# Linas AI Constitution — AI-first (Mahmoud / boc system)

Canonical Cursor rule: `.cursor/rules/linas-ai-constitution.mdc` (`alwaysApply`).

## Role of the system (runtime)

The runtime system is a tool executor and transport layer around AI.

It may:

- deliver inbound messages TO the AI (Customer Terra / Owner Sol / planners / tools),
- execute only what the AI explicitly requests via tools (send, retrieve, persist, escalate, cancel follow-up, etc.),
- enforce OpenAI/platform safety / ban / ToS blocks (provider refusal) — the ONLY allowed reason to withhold a message from the AI model,
- enforce auth, tenant isolation, billing holds, rate limits, unpublished-tenant gates (infrastructure — not “what to say”).

It must NEVER:

- Author customer-facing or owner-facing reply text from templates/keywords/regex (Terra/Sol author; FAQ owner-verbatim is tenant CM content, not system invention).
- Tell the AI what words to say via canned system replies that replace the model.
- Block, short-circuit, refuse, rewrite, or re-route a message away from Customer AI or Owner Copilot based on keyword lists, regex lexicons, or heuristic token catalogs.
- Override an AI planner/tool decision with keyword/regex “force-correct” overlays.
- Introduce new BUSINESS_SCOPE / greeting-only / creative-keyword / anger-keyword / assent-keyword / audience-keyword / catalog-intent-regex / price-intent-regex / human-detect lexicons that gate AI.

## Allowed non-AI exceptions (narrow)

- Smart Follow-up STOP/opt-out may cancel marketing follow-up sequences after the inbound already reached (or in parallel with) Terra — it must NEVER prevent Customer AI from seeing the message, and must NEVER send canned customer copy.
- Pure infra: auth, tenant ACL, ledger/billing, OpenAI safety, outbox transport, durable_flags HA checks.

## Future Cursor / engineers

FORBIDDEN forever to add keyword/regex gates that decide for Terra or Sol.
If you need new behavior: put it in the model prompt, tenant CM, or an AI tool — not a token list that halts the pipeline.
Comment surface replies are public-thread authored by Terra; system never authors comment copy; no keyword gates.
Customer inbound: one Terra agent session per turn. System retrieves evidence and executes allowlisted tools only. No separate planner / request-round / tool-picker / greeting LLM. No feature flag.

## KEEP (do not misuse)

- `services/smart_followup/opt_out.py` — STOP phrases cancel SFU sequences only; never block Terra inbound; never author customer text.
- Auth, tenant isolation, billing ledger, OpenAI API safety errors, unpublished tenant gate, outbox send **after** an AI tool request.
- FAQ owner-verbatim from tenant CM (`services/faq/cm_faq.py` / `services/brain/faq_exact.py`).
- Evidence-only Terra SYSTEM/RULES (constrain invented facts; they do not keyword-gate inbound).
- Tool schemas and registry hard-disable of cancelled creative tools (infra). Sol still sees the message and refuses in natural language.
- Restricted topics from **tenant CM**, not a system lexicon.
- `services/ai_setup/durable_flags.py` HA/QG bridge.

## Product law

1. Customer inbound always reaches Terra except OpenAI safety / unpublished tenant / auth / billing hard fail. No keyword refuse with `ai_called=False`.
2. Owner inbound always reaches Sol LLM/tools except auth / safety. No creative keyword pre-refuse.
3. System outbound customer/owner text only when AI (or explicit owner UI Approve) requested the send/confirm tool — never from scope-guard templates.
4. Planner: OpenAI/GPT plan is authoritative. No regex overlay force-corrections.
5. No production deploy is implied by constitution-only PRs.
