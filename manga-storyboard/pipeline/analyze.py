"""Analyze transcript → brief + gap questions."""

from __future__ import annotations

from typing import Any

from pipeline.roles import ANALYZE_SYSTEM, ANALYZE_USER, FOLLOWUP_SYSTEM, FOLLOWUP_USER, library_summary
from pipeline.router import DirectorRouter
from pipeline.style_library import load_library
from pipeline.util import parse_json


def analyze_transcript(
    router: DirectorRouter,
    transcript: str,
    aesthetic: str,
) -> dict[str, Any]:
    lib = load_library()
    raw = router.complete(
        "director",
        ANALYZE_SYSTEM,
        ANALYZE_USER.format(
            transcript=transcript[:50000],
            library_summary=library_summary(lib),
            aesthetic=aesthetic,
        ),
        json_mode=True,
        temperature=0.3,
    )
    data = parse_json(raw)
    data.setdefault("questions", [])
    data.setdefault("ready", not data.get("questions"))
    data.setdefault("brief", {})
    brief = data["brief"]
    brief.setdefault("aesthetic", aesthetic)
    return data


def apply_answers(
    router: DirectorRouter,
    analysis: dict[str, Any],
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    lib = load_library()
    raw = router.complete(
        "director",
        FOLLOWUP_SYSTEM,
        FOLLOWUP_USER.format(
            analysis=str(analysis)[:20000],
            answers=str(answers),
            library_summary=library_summary(lib),
        ),
        json_mode=True,
        temperature=0.3,
    )
    data = parse_json(raw)
    data.setdefault("questions", [])
    data.setdefault("ready", not data.get("questions"))
    # Merge brief into analysis for continuity
    if "brief" in data:
        analysis = {**analysis, "brief": data["brief"], "questions": data["questions"], "ready": data["ready"]}
        analysis["followup_notes"] = data.get("notes", "")
    return analysis
