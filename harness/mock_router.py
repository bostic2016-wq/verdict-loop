"""Deterministic fake router for offline smoke tests (no API keys)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MockRouter:
    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = settings or {}
        self.models = (settings or {}).get("models", {})
        self.calls: list[str] = []

    def model_for(self, role: str) -> str:
        return self.models.get(role, f"mock/{role}")

    def complete(
        self,
        role: str,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append(role)
        if role == "scout":
            return json.dumps(
                {
                    "summary": "Mock research summary for smoke test.",
                    "supporting_points": ["Clear demand signal", "Low startup cost"],
                    "risks": ["Time cost", "Audience acquisition"],
                    "open_questions": ["How many hours per week?"],
                    "assumptions": ["User can ship an MVP in 2 weeks"],
                }
            )
        if role == "advocate":
            return "Advocate: This plan has upside with manageable downside if scoped tightly."
        if role == "skeptic":
            return "Skeptic: Execution risk and attention cost are underweighted."
        if role == "judge":
            return json.dumps(
                {
                    "score": 8,
                    "recommendation": "only_if",
                    "conditions": ["Ship a 4-week experiment", "Define a cancel rule"],
                    "reasoning": "Balanced case; proceed only with a short test.",
                    "bottom_line": "Try a 4-week test with a clear cancel rule.",
                    "focus_questions": [],
                    "continue": False,
                }
            )
        if role == "promoter":
            return json.dumps(
                {
                    "headline": "Try it for four weeks",
                    "tagline": "Small test. Clear cancel rule.",
                    "promo_blurb": "A calm mock promo for smoke testing the creative loop.",
                    "images": [
                        {
                            "id": "hero",
                            "purpose": "hero",
                            "prompt": "soft daylight desk with notebook and coffee, minimal photo",
                            "negative_notes": "no logos",
                        },
                        {
                            "id": "social",
                            "purpose": "social",
                            "prompt": "square social graphic style abstract soft green shapes",
                            "negative_notes": "no tiny text",
                        },
                    ],
                }
            )
        return f"mock:{role}"

    def complete_vision(
        self,
        role: str,
        system: str,
        user: str,
        image_path: Path,
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
    ) -> str:
        self.calls.append(f"{role}:vision")
        # Pass if file exists and has bytes.
        ok = image_path.exists() and image_path.stat().st_size > 100
        return json.dumps(
            {
                "score": 8 if ok else 3,
                "pass": ok,
                "issues": [] if ok else ["missing or empty image"],
                "rewrite_notes": "" if ok else "Regenerate with clearer subject",
            }
        )