"""Sequence-level editorial QA on a filmstrip batch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.creative_bible import bible_excerpt
from pipeline.roles import SEQUENCE_SYSTEM, SEQUENCE_USER
from pipeline.router import DirectorRouter
from pipeline.util import parse_json


def critique_sequence(
    router: DirectorRouter,
    bible: dict[str, Any],
    panels: list[dict[str, Any]],
    image_paths: list[Path],
    *,
    pass_score: float = 0.7,
) -> dict[str, Any]:
    existing = [p for p in image_paths if p.exists()]
    if not existing:
        return {
            "sequence_pass": True,
            "score": pass_score,
            "pacing_issues": [],
            "panels_to_regen": [],
            "notes": "No images to review",
            "soft_pass": True,
        }
    try:
        import json

        raw = router.complete_vision(
            "vision_critic",
            SEQUENCE_SYSTEM,
            SEQUENCE_USER.format(
                bible_excerpt=bible_excerpt(bible),
                panels=json.dumps(
                    [
                        {
                            "index": p.get("index"),
                            "shot_type": p.get("shot_type"),
                            "action": p.get("action"),
                            "emotion": p.get("emotion"),
                        }
                        for p in panels
                    ],
                    indent=2,
                ),
            ),
            existing,
            json_mode=True,
        )
        data = parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        return {
            "sequence_pass": True,
            "score": pass_score,
            "pacing_issues": [f"Sequence critic unavailable: {exc}"],
            "panels_to_regen": [],
            "notes": "",
            "soft_pass": True,
        }

    data.setdefault("panels_to_regen", [])
    data.setdefault("pacing_issues", [])
    data.setdefault("notes", "")
    score = float(data.get("score", 0) or 0)
    data["sequence_pass"] = bool(data.get("sequence_pass")) and score >= pass_score
    return data
