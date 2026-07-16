"""Follow-up Q&A grounded in a prior Verdict Loop run (session memory)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.router import ModelRouter


FOLLOWUP_SYSTEM = """You are Verdict Loop's follow-up assistant.
Answer the user's question using ONLY the provided run context (claim, verdict, conditions, research notes, debate summaries, and any VERIFIED MONEY MATH).
If the answer is not in the context, say what is missing — do not invent facts.
For money questions: use VERIFIED MONEY MATH numbers exactly; never invent a different after-tax figure.
Keep answers short and clear unless the user asks for detail.
If the context includes two compared plans (A and B), say which plan you are referring to.
"""


def build_run_context(result: dict[str, Any], *, detail: str = "brief") -> str:
    """Compress a pipeline result into prompt context."""
    if result.get("mode") == "compare":
        return _compare_context(result, detail=detail)

    debate = result.get("debate") or {}
    verdict = debate.get("verdict") or {}
    notes = debate.get("final_notes") or {}
    parts = [
        f"CLAIM:\n{result.get('claim', '')}",
        f"VERDICT: {verdict.get('recommendation')} (score {verdict.get('score')})",
        f"BOTTOM LINE: {verdict.get('bottom_line') or verdict.get('reasoning') or ''}",
        "CONDITIONS:\n- " + "\n- ".join(verdict.get("conditions") or ["(none)"]),
    ]
    money = result.get("money_facts")
    if money and money.get("has_money_signal"):
        from harness.money import format_money_block

        parts.append(format_money_block(money))
    if notes:
        parts.append(f"RESEARCH SUMMARY:\n{notes.get('summary', '')}")
        if detail == "detailed":
            parts.append(
                "SUPPORTING:\n- "
                + "\n- ".join((notes.get("supporting_points") or [])[:8])
            )
            parts.append("RISKS:\n- " + "\n- ".join((notes.get("risks") or [])[:8]))
        else:
            parts.append(
                "TOP SUPPORT:\n- "
                + "\n- ".join((notes.get("supporting_points") or [])[:3])
            )
            parts.append("TOP RISKS:\n- " + "\n- ".join((notes.get("risks") or [])[:3]))

    rounds = debate.get("rounds") or []
    if rounds and detail == "detailed":
        last = rounds[-1]
        parts.append(f"ADVOCATE (last round):\n{(last.get('advocate') or '')[:1200]}")
        parts.append(f"SKEPTIC (last round):\n{(last.get('skeptic') or '')[:1200]}")
    elif rounds:
        last = rounds[-1]
        parts.append(f"ADVOCATE (abbrev):\n{(last.get('advocate') or '')[:400]}")
        parts.append(f"SKEPTIC (abbrev):\n{(last.get('skeptic') or '')[:400]}")
    return "\n\n".join(parts)


def _compare_context(result: dict[str, Any], *, detail: str) -> str:
    a = result.get("result_a") or {}
    b = result.get("result_b") or {}
    pick = result.get("pick") or ""
    return (
        "MODE: compare two plans\n\n"
        "=== PLAN A ===\n"
        + build_run_context({**a, "mode": "single"}, detail=detail)
        + "\n\n=== PLAN B ===\n"
        + build_run_context({**b, "mode": "single"}, detail=detail)
        + f"\n\nPICK SUMMARY:\n{pick}"
    )


def answer_followup(
    router: ModelRouter,
    result: dict[str, Any],
    question: str,
    history: list[dict[str, str]] | None = None,
    *,
    detail: str = "brief",
) -> str:
    ctx = build_run_context(result, detail=detail)
    history = history or []
    hist_txt = ""
    if history:
        lines = []
        for m in history[-8:]:
            role = m.get("role", "user")
            lines.append(f"{role.upper()}: {m.get('content', '')}")
        hist_txt = "PRIOR FOLLOW-UPS:\n" + "\n".join(lines) + "\n\n"
    user = (
        f"RUN CONTEXT:\n{ctx}\n\n"
        f"{hist_txt}"
        f"USER QUESTION:\n{question.strip()}\n\n"
        "Answer briefly and grounded in the context."
    )
    return router.complete(
        "judge",
        FOLLOWUP_SYSTEM,
        user,
        temperature=0.3,
        max_tokens=700,
    )


def pick_between_plans(
    router: ModelRouter,
    result_a: dict[str, Any],
    result_b: dict[str, Any],
) -> str:
    """One-line style pick after a compare run."""
    va = (result_a.get("debate") or {}).get("verdict") or {}
    vb = (result_b.get("debate") or {}).get("verdict") or {}
    user = (
        f"PLAN A:\n{result_a.get('claim')}\n"
        f"Verdict: {va.get('recommendation')} score {va.get('score')}\n"
        f"Why: {va.get('bottom_line') or va.get('reasoning')}\n"
        f"Conditions: {va.get('conditions')}\n\n"
        f"PLAN B:\n{result_b.get('claim')}\n"
        f"Verdict: {vb.get('recommendation')} score {vb.get('score')}\n"
        f"Why: {vb.get('bottom_line') or vb.get('reasoning')}\n"
        f"Conditions: {vb.get('conditions')}\n\n"
        "In 2-3 sentences: which plan is stronger overall and why? "
        "If close, say so and name the deciding factor."
    )
    return router.complete(
        "judge",
        "You compare two Verdict Loop outcomes. Be direct and fair. No JSON.",
        user,
        temperature=0.2,
        max_tokens=300,
    )


def suggested_followups(result: dict[str, Any]) -> list[str]:
    """Candidate clarifying questions the app can ask the user (system-led)."""
    suggestions: list[str] = []
    if result.get("mode") == "compare":
        suggestions.extend(
            [
                "Which outcome matters more to you right now — upside or risk control?",
                "What is your hard deadline for choosing between Plan A and Plan B?",
                "What constraint would make you drop one plan entirely?",
            ]
        )
        return suggestions[:5]

    verdict = ((result.get("debate") or {}).get("verdict") or {})
    for q in verdict.get("focus_questions") or []:
        q = str(q).strip()
        if q and q not in suggestions:
            # Turn model focus items into questions asked TO the user
            if not q.endswith("?"):
                q = q.rstrip(".") + "?"
            suggestions.append(q)
    money = result.get("money_facts") or {}
    if money.get("has_money_signal"):
        if money.get("missing"):
            suggestions.append(
                "Can you share the tax details still missing so I can lock the after-tax math?"
            )
        else:
            suggestions.append(
                "Does the verified after-tax figure match what you expected to take home?"
            )
    suggestions.extend(
        [
            "What would have to be true for you to feel good moving forward this week?",
            "What is the one risk you are most worried about underestimating?",
        ]
    )
    out: list[str] = []
    for s in suggestions:
        if s not in out:
            out.append(s)
    return out[:6]


def opening_question(result: dict[str, Any]) -> str:
    """First question the app asks the user after a verdict."""
    qs = suggested_followups(result)
    return qs[0] if qs else "What part of this verdict do you want to pressure-test first?"


def append_followup(run_dir: str | Path, question: str, answer: str) -> None:
    path = Path(run_dir) / "followups.json"
    data: list[dict[str, str]] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
    data.append({"role": "user", "content": question})
    data.append({"role": "assistant", "content": answer})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
