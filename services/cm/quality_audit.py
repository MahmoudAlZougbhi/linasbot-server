"""Proactive CM quality pass for Owner Copilot (critique beyond fill/missing).

Returns compact findings — never full CM dumps. Severity-ordered, capped.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from services.cm.constants import CM_SECTIONS
from services.cm.progress import list_section_fill_status, progress_summary
from services.cm.storage import get_draft

_MAX_FINDINGS = 18

_SUSPICIOUS_RE = re.compile(
    r"\b(tbd|todo|lorem|ipsum|placeholder|xxx+|test\s*test|asdf|qwerty|sample\s*only)\b|"
    r"(غير\s*محدد|سيتم\s*التحديث|لاحقاً|لاحقا|coming\s*soon)",
    re.I,
)
_NORM_WS = re.compile(r"\s+")


def _norm(text: Any) -> str:
    return _NORM_WS.sub(" ", str(text or "").strip().lower())


def _label_blob(labels: Any) -> str:
    if not isinstance(labels, dict):
        return ""
    return " ".join(str(labels.get(k) or "") for k in ("ar", "en", "fr", "franco")).strip()


def _payload(tenant_id: str, section: str) -> dict[str, Any] | None:
    env = get_draft(section, tenant_id=tenant_id, create_default=False)
    if env is None or not isinstance(env.payload, dict):
        return None
    return env.payload


def _finding(
    *,
    category: str,
    severity: str,
    section: str,
    title: str,
    detail: str,
    hint: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "category": category,
        "severity": severity,
        "section": section,
        "title": title,
        "detail": detail,
    }
    if hint:
        row["hint"] = hint
    return row


def _scan_fill_gaps(tenant_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in list_section_fill_status(tenant_id, create_missing=False):
        fill = str(row.get("fill") or "")
        section = str(row.get("section") or "")
        if fill == "missing":
            out.append(
                _finding(
                    category="missing",
                    severity="high",
                    section=section,
                    title=f"{section} still empty",
                    detail=str(row.get("summary") or "Factory default — not filled yet."),
                    hint="Fill via propose_cm_patch → Approve → Live, or cm_fill_plan.",
                )
            )
        elif fill == "weak":
            gaps = ", ".join(str(g) for g in (row.get("gaps") or [])[:4]) or "incomplete"
            out.append(
                _finding(
                    category="weak_incomplete",
                    severity="high",
                    section=section,
                    title=f"{section} is weak / incomplete",
                    detail=f"{row.get('summary') or 'Incomplete.'} Gaps: {gaps}.",
                    hint="Strengthen this section before relying on customer answers.",
                )
            )
    return out


def _scan_validation(tenant_id: str) -> list[dict[str, Any]]:
    from services.cm.validation import validate_cm

    result = validate_cm(tenant_id=tenant_id)
    out: list[dict[str, Any]] = []
    for issue in list(result.get("errors") or [])[:8]:
        if not isinstance(issue, dict):
            continue
        out.append(
            _finding(
                category="contradiction",
                severity="high",
                section=str(issue.get("section") or "cm"),
                title="Hard conflict / validation error",
                detail=str(issue.get("message") or issue.get("code") or "validation error"),
                hint="Fix before publish; propose_cm_patch with force_edit if section is DONE.",
            )
        )
    for issue in list(result.get("warnings") or [])[:4]:
        if not isinstance(issue, dict):
            continue
        out.append(
            _finding(
                category="contradiction",
                severity="medium",
                section=str(issue.get("section") or "cm"),
                title="Validation warning",
                detail=str(issue.get("message") or issue.get("code") or "warning"),
            )
        )
    return out


def _scan_faq_duplicates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        gid = str(item.get("qa_group_id") or item.get("id") or "?")
        for v in item.get("variants") or []:
            if not isinstance(v, dict):
                continue
            q = _norm(v.get("question"))
            if len(q) < 4:
                continue
            lang = str(v.get("language") or "")
            buckets[f"{lang}::{q}"].append(gid)
    out: list[dict[str, Any]] = []
    for key, ids in buckets.items():
        uniq = sorted(set(ids))
        if len(uniq) < 2:
            continue
        lang, q = key.split("::", 1)
        out.append(
            _finding(
                category="duplicate",
                severity="high",
                section="faq",
                title="Duplicate FAQ questions",
                detail=f"Same {lang or 'any'} question in groups {', '.join(uniq[:4])}: “{q[:80]}”.",
                hint="Merge or delete duplicates — Smart Q&A may match unpredictably.",
            )
        )
        if len(out) >= 5:
            break
    return out


def _scan_title_duplicates(section: str, payload: dict[str, Any], *, title_key: str = "title") -> list[dict[str, Any]]:
    seen: dict[str, list[str]] = defaultdict(list)
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        title = _norm(item.get(title_key) or _label_blob(item.get("labels")))
        if len(title) < 3:
            continue
        iid = str(item.get("id") or item.get("qa_group_id") or title[:24])
        seen[title].append(iid)
    out: list[dict[str, Any]] = []
    for title, ids in seen.items():
        uniq = sorted(set(ids))
        if len(uniq) < 2:
            continue
        out.append(
            _finding(
                category="duplicate",
                severity="medium",
                section=section,
                title=f"Duplicate {section} titles",
                detail=f"“{title[:80]}” appears {len(uniq)} times ({', '.join(uniq[:4])}).",
                hint="Deduplicate or clarify so retrieval does not confuse customers.",
            )
        )
        if len(out) >= 4:
            break
    return out


def _scan_text_quality(section: str, texts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """texts: list of (item_id, body)."""
    out: list[dict[str, Any]] = []
    for iid, body in texts:
        raw = str(body or "").strip()
        if not raw:
            continue
        if _SUSPICIOUS_RE.search(raw):
            out.append(
                _finding(
                    category="suspicious",
                    severity="high",
                    section=section,
                    title="Suspicious / placeholder content",
                    detail=f"Item `{iid}` looks like placeholder or unfinished text.",
                    hint="Replace with real business facts before going Live.",
                )
            )
        elif len(raw) < 24:
            out.append(
                _finding(
                    category="unclear",
                    severity="medium",
                    section=section,
                    title="Very short / unclear content",
                    detail=f"Item `{iid}` is only {len(raw)} chars — likely confusing for customers.",
                    hint="Expand with clear, concrete wording (halwse).",
                )
            )
        if len(out) >= 6:
            break
    return out


def _scan_section_content(tenant_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    faq = _payload(tenant_id, "faq")
    if faq:
        out.extend(_scan_faq_duplicates(faq))
        texts: list[tuple[str, str]] = []
        for item in faq.get("items") or []:
            if not isinstance(item, dict):
                continue
            gid = str(item.get("qa_group_id") or "?")
            for v in item.get("variants") or []:
                if isinstance(v, dict) and v.get("answer"):
                    texts.append((f"{gid}:{v.get('language')}", str(v.get("answer"))))
        out.extend(_scan_text_quality("faq", texts))

    for section in ("knowledge", "care"):
        payload = _payload(tenant_id, section)
        if not payload:
            continue
        out.extend(_scan_title_duplicates(section, payload))
        texts = []
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            texts.append((str(item.get("id") or item.get("title") or "?"), str(item.get("body") or "")))
        out.extend(_scan_text_quality(section, texts))

    services = _payload(tenant_id, "services")
    if services:
        out.extend(_scan_title_duplicates("services", services))

    style = _payload(tenant_id, "style")
    if style:
        body = str(style.get("style_body") or style.get("tone") or "")
        out.extend(_scan_text_quality("style", [("style", body)]))

    ai_basics = _payload(tenant_id, "ai_basics")
    if ai_basics:
        blob = " ".join(
            str(ai_basics.get(k) or "")
            for k in ("ai_role", "business_purpose", "short_introduction", "identity_summary", "advanced_instructions")
        )
        out.extend(_scan_text_quality("ai_basics", [("identity", blob)]))

    return out


def _scan_improve_opportunities(tenant_id: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    done = set(summary.get("done_sections") or [])
    services = _payload(tenant_id, "services")
    prices = _payload(tenant_id, "prices")
    if "services" in done and services:
        svc_n = len([it for it in (services.get("items") or []) if isinstance(it, dict)])
        has_prices = False
        if isinstance(prices, dict):
            has_prices = any(
                isinstance(prices.get(k), list) and prices.get(k) for k in ("catalog", "price_entries", "items")
            ) or bool(str(prices.get("policy_text") or "").strip())
        if svc_n and not has_prices and "prices" not in done:
            out.append(
                _finding(
                    category="improve",
                    severity="medium",
                    section="prices",
                    title="Services without prices",
                    detail=f"{svc_n} service(s) filled but prices still empty — AI cannot quote numbers safely.",
                    hint="Add catalog entries or a clear price policy.",
                )
            )

    faq = _payload(tenant_id, "faq")
    if faq and "faq" in done:
        thin = 0
        for item in faq.get("items") or []:
            if not isinstance(item, dict):
                continue
            langs = {
                str(v.get("language"))
                for v in (item.get("variants") or [])
                if isinstance(v, dict) and str(v.get("question") or "").strip() and str(v.get("answer") or "").strip()
            }
            if 0 < len(langs) < 2:
                thin += 1
        if thin:
            out.append(
                _finding(
                    category="improve",
                    severity="low",
                    section="faq",
                    title="FAQ language coverage thin",
                    detail=f"{thin} FAQ group(s) only have one language variant — consider ar/en/fr/franco.",
                    hint="propose_smart_answer auto-translates on Approve for new pairs.",
                )
            )

    if "branches" in done and "opening_hours" not in done:
        out.append(
            _finding(
                category="improve",
                severity="medium",
                section="opening_hours",
                title="Locations without opening hours",
                detail="Locations are filled but hours are not — customers will ask when you are open.",
                hint="Add named Mon–Sun schedules.",
            )
        )
    return out


def _rank_key(f: dict[str, Any]) -> tuple[int, int]:
    sev = {"high": 0, "medium": 1, "low": 2}.get(str(f.get("severity")), 3)
    cat = {
        "contradiction": 0,
        "suspicious": 1,
        "duplicate": 2,
        "weak_incomplete": 3,
        "missing": 4,
        "unclear": 5,
        "improve": 6,
    }.get(str(f.get("category")), 9)
    return (sev, cat)


def run_cm_quality_audit(tenant_id: str, *, section: str | None = None) -> dict[str, Any]:
    """Compact proactive quality pass over CM drafts (no full body dump)."""
    summary = progress_summary(tenant_id, create_missing=False)
    findings: list[dict[str, Any]] = []
    findings.extend(_scan_fill_gaps(tenant_id))
    findings.extend(_scan_validation(tenant_id))
    findings.extend(_scan_section_content(tenant_id))
    findings.extend(_scan_improve_opportunities(tenant_id, summary))

    focus = (section or "").strip().replace("-", "_") or None
    if focus and focus in CM_SECTIONS:
        # Keep focus section first, but still include cross-cutting issues.
        focused = [f for f in findings if f.get("section") == focus]
        other = [f for f in findings if f.get("section") != focus]
        findings = focused + other

    findings = sorted(findings, key=_rank_key)[:_MAX_FINDINGS]
    counts: dict[str, int] = defaultdict(int)
    for f in findings:
        counts[str(f.get("category"))] += 1

    return {
        "quality_pass": True,
        "finding_count": len(findings),
        "counts_by_category": dict(counts),
        "findings": findings,
        "checklist": [
            "critique / what’s wrong",
            "duplicates",
            "unclear / confusing wording",
            "improvement opportunities (halwse)",
            "suspicious / placeholder / outdated-looking content",
            "contradictions / validation conflicts",
        ],
        "report_style": (
            "Answer the owner's specific ask first. Then give a ChatGPT-style editor critique "
            "from findings (top issues only). Do NOT dump full CM. Offer propose→Approve→Live fixes."
        ),
    }
