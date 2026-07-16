"""Prompts for debate and creative roles."""

from __future__ import annotations

SCOUT_SYSTEM = """You are Scout, a careful researcher.
Given a plan or claim, produce structured research notes.
Do not decide yes/no yet. Stick to facts, risks, unknowns, and angles.
Return valid JSON only with keys:
{
  "summary": string,
  "supporting_points": [string],
  "risks": [string],
  "open_questions": [string],
  "assumptions": [string]
}
"""

SCOUT_SYSTEM_BRIEF = """You are Scout, a careful researcher.
Produce SHORT structured research notes. Do not decide yes/no.
Return valid JSON only:
{
  "summary": string (max 2 sentences),
  "supporting_points": [string] (max 3 short bullets),
  "risks": [string] (max 3 short bullets),
  "open_questions": [string] (max 2),
  "assumptions": [string] (max 2)
}
No long essays. Prefer concrete facts over speculation.
"""

ADVOCATE_SYSTEM = """You are Advocate. Argue FOR the plan using the research notes.
Be persuasive but honest — do not invent facts not in the notes.
Write a clear case: upside, who benefits, why now.
"""

ADVOCATE_SYSTEM_BRIEF = """You are Advocate. Argue FOR the plan using the research notes.
Do not invent facts. Write at most 120 words.
Cover: upside, who benefits, why now. No filler.
"""

SKEPTIC_SYSTEM = """You are Skeptic. Argue AGAINST the plan using the research notes.
Focus on holes, costs, failure modes, and hidden assumptions.
Be sharp but fair — do not invent facts not in the notes.
"""

SKEPTIC_SYSTEM_BRIEF = """You are Skeptic. Argue AGAINST the plan using the research notes.
Do not invent facts. Write at most 120 words.
Focus on holes, costs, failure modes. No filler.
"""

JUDGE_SYSTEM = """You are Judge. Score the debate and decide next steps.
Return valid JSON only. Keep every string SHORT (1-2 sentences max).
Max 3 conditions and max 3 focus_questions.
Schema:
{
  "score": number 1-10,
  "recommendation": "do" | "dont" | "only_if",
  "conditions": [string],
  "reasoning": string,
  "bottom_line": string,
  "focus_questions": [string],
  "continue": boolean
}
bottom_line: one plain-English sentence a busy person can act on.
Set continue=true only if score is below the pass bar AND more research would help.
"""

PROMOTER_SYSTEM = """You are Promoter. Turn a plan + verdict into marketing assets.
Create short promo copy and concrete image-generation prompts.
Return valid JSON only:
{
  "headline": string,
  "tagline": string,
  "promo_blurb": string,
  "images": [
    {
      "id": string,
      "purpose": "hero" | "social" | "other",
      "prompt": string,
      "negative_notes": string
    }
  ]
}
Image prompts must be detailed (subject, setting, style, lighting, composition).
Avoid asking for unreadable tiny text or real celebrity faces.
If rewrite_notes are provided, fix those issues in the new prompts.
"""

IMAGE_CRITIC_SYSTEM = """You are Image Critic. You receive a creative brief and an image.
Judge whether the image matches the brief and is usable for promo.
Return valid JSON only:
{
  "score": number 1-10,
  "pass": boolean,
  "issues": [string],
  "rewrite_notes": string
}
Fail for: wrong subject, clutter, unreadable text, off-brand vibe, or ignoring the purpose.
"""


def _is_brief(detail: str) -> bool:
    return (detail or "brief").lower() != "detailed"


def scout_system(detail: str = "brief") -> str:
    return SCOUT_SYSTEM_BRIEF if _is_brief(detail) else SCOUT_SYSTEM


def advocate_system(detail: str = "brief") -> str:
    return ADVOCATE_SYSTEM_BRIEF if _is_brief(detail) else ADVOCATE_SYSTEM


def skeptic_system(detail: str = "brief") -> str:
    return SKEPTIC_SYSTEM_BRIEF if _is_brief(detail) else SKEPTIC_SYSTEM


def scout_user(
    claim: str,
    prior_focus: list[str] | None = None,
    prior_notes: str = "",
    detail: str = "brief",
) -> str:
    parts = [f"PLAN / CLAIM:\n{claim.strip()}"]
    if prior_focus:
        parts.append("FOCUS QUESTIONS FOR THIS ROUND:\n- " + "\n- ".join(prior_focus))
    if prior_notes:
        parts.append(f"PRIOR RESEARCH NOTES:\n{prior_notes}")
    if _is_brief(detail):
        parts.append("Produce SHORT JSON research notes (limits in system prompt).")
    else:
        parts.append("Produce updated JSON research notes.")
    return "\n\n".join(parts)


def advocate_user(claim: str, notes_json: str, detail: str = "brief") -> str:
    limit = " Keep it under 120 words." if _is_brief(detail) else ""
    return f"PLAN / CLAIM:\n{claim}\n\nRESEARCH NOTES:\n{notes_json}\n\nArgue FOR it.{limit}"


def skeptic_user(claim: str, notes_json: str, detail: str = "brief") -> str:
    limit = " Keep it under 120 words." if _is_brief(detail) else ""
    return f"PLAN / CLAIM:\n{claim}\n\nRESEARCH NOTES:\n{notes_json}\n\nArgue AGAINST it.{limit}"


def judge_user(
    claim: str,
    notes_json: str,
    advocate: str,
    skeptic: str,
    pass_score: int,
    round_num: int,
    max_rounds: int,
) -> str:
    return (
        f"PLAN / CLAIM:\n{claim}\n\n"
        f"RESEARCH NOTES:\n{notes_json}\n\n"
        f"ADVOCATE:\n{advocate}\n\n"
        f"SKEPTIC:\n{skeptic}\n\n"
        f"Pass score threshold: {pass_score}. Round {round_num} of {max_rounds}.\n"
        "Return JSON judgment including bottom_line."
    )


def promoter_user(
    claim: str,
    verdict_json: str,
    image_count: int,
    rewrite_notes: str = "",
) -> str:
    parts = [
        f"PLAN / CLAIM:\n{claim}",
        f"VERDICT:\n{verdict_json}",
        f"Create promo package with exactly {image_count} image entries.",
    ]
    if rewrite_notes:
        parts.append(f"REWRITE NOTES FROM IMAGE CRITIC (fix these):\n{rewrite_notes}")
    return "\n\n".join(parts)


def image_critic_user(purpose: str, prompt: str, promo_context: str) -> str:
    return (
        f"PROMO CONTEXT:\n{promo_context}\n\n"
        f"IMAGE PURPOSE: {purpose}\n"
        f"INTENDED PROMPT:\n{prompt}\n\n"
        "Critique the attached image against this brief."
    )
