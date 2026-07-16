from __future__ import annotations

import json
from typing import Any, Callable

from harness import roles
from harness.research import normalize_notes
from harness.router import ModelRouter, parse_json


ProgressCb = Callable[[str, dict[str, Any]], None]


def _trim_notes_brief(notes: dict[str, Any]) -> dict[str, Any]:
    out = dict(notes)
    for key, n in (
        ("supporting_points", 3),
        ("risks", 3),
        ("open_questions", 2),
        ("assumptions", 2),
    ):
        vals = list(out.get(key) or [])
        out[key] = vals[:n]
    summary = str(out.get("summary") or "")
    if len(summary) > 400:
        out["summary"] = summary[:397].rstrip() + "…"
    return out


def run_debate(
    claim: str,
    router: ModelRouter,
    settings: dict[str, Any],
    on_progress: ProgressCb | None = None,
    *,
    detail: str = "brief",
) -> dict[str, Any]:
    debate_cfg = settings.get("debate", {})
    detail = (detail or debate_cfg.get("detail") or "brief").lower()
    if detail not in {"brief", "detailed"}:
        detail = "brief"
    max_rounds = int(debate_cfg.get("max_rounds", 3))
    if detail == "brief":
        max_rounds = min(max_rounds, int(debate_cfg.get("brief_max_rounds", 1)))
    pass_score = int(debate_cfg.get("pass_score", 8))

    def emit(event: str, payload: dict[str, Any]) -> None:
        if on_progress:
            on_progress(event, payload)

    rounds: list[dict[str, Any]] = []
    notes: dict[str, Any] | None = None
    judgment: dict[str, Any] | None = None
    focus: list[str] = []

    for round_num in range(1, max_rounds + 1):
        emit("scout_start", {"round": round_num})
        prior = json.dumps(notes, indent=2) if notes else ""
        scout_raw = router.complete(
            "scout",
            roles.scout_system(detail),
            roles.scout_user(
                claim, prior_focus=focus or None, prior_notes=prior, detail=detail
            ),
            json_mode=True,
        )
        notes = normalize_notes(parse_json(scout_raw))
        if detail == "brief":
            notes = _trim_notes_brief(notes)
        notes_json = json.dumps(notes, indent=2)
        emit("scout_done", {"round": round_num, "notes": notes})

        emit("advocate_start", {"round": round_num})
        advocate = router.complete(
            "advocate",
            roles.advocate_system(detail),
            roles.advocate_user(claim, notes_json, detail=detail),
            temperature=0.5,
            max_tokens=400 if detail == "brief" else 1024,
        )
        emit("advocate_done", {"round": round_num, "text": advocate})

        emit("skeptic_start", {"round": round_num})
        skeptic = router.complete(
            "skeptic",
            roles.skeptic_system(detail),
            roles.skeptic_user(claim, notes_json, detail=detail),
            temperature=0.5,
            max_tokens=400 if detail == "brief" else 1024,
        )
        emit("skeptic_done", {"round": round_num, "text": skeptic})

        emit("judge_start", {"round": round_num})
        judge_raw = router.complete(
            "judge",
            roles.JUDGE_SYSTEM,
            roles.judge_user(
                claim, notes_json, advocate, skeptic, pass_score, round_num, max_rounds
            ),
            json_mode=True,
            temperature=0.2,
            max_tokens=4096,
        )
        try:
            judgment = parse_json(judge_raw)
        except ValueError:
            compact_user = (
                f"Your previous JSON was truncated or invalid.\n"
                f"Return ONLY compact valid JSON with keys "
                f"score,recommendation,conditions,reasoning,bottom_line,focus_questions,continue.\n"
                f"Keep reasoning under 40 words. Max 2 conditions.\n"
                f"Previous attempt:\n{judge_raw[:1200]}"
            )
            judge_raw = router.complete(
                "judge",
                roles.JUDGE_SYSTEM,
                compact_user,
                json_mode=True,
                temperature=0.1,
                max_tokens=4096,
            )
            judgment = parse_json(judge_raw)
        if not isinstance(judgment, dict):
            judgment = {
                "score": 0,
                "recommendation": "only_if",
                "reasoning": str(judgment),
            }
        if not judgment.get("bottom_line"):
            judgment["bottom_line"] = judgment.get("reasoning") or ""
        score = float(judgment.get("score", 0) or 0)
        should_continue = bool(judgment.get("continue", False)) and score < pass_score
        if round_num >= max_rounds:
            should_continue = False
        judgment["continue"] = should_continue

        round_record = {
            "round": round_num,
            "notes": notes,
            "advocate": advocate,
            "skeptic": skeptic,
            "judgment": judgment,
        }
        rounds.append(round_record)
        emit("judge_done", {"round": round_num, "judgment": judgment})

        if not should_continue:
            break
        focus = list(judgment.get("focus_questions") or [])

    assert notes is not None and judgment is not None
    return {
        "claim": claim,
        "rounds": rounds,
        "final_notes": notes,
        "verdict": judgment,
        "pass_score": pass_score,
        "detail": detail,
    }
