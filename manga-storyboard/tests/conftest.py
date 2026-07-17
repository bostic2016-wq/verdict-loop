"""Shared fixtures for the button smoke loop and QA unit tests.

Everything runs under mock mode with the pipeline patched, so no test ever
calls OpenRouter/Seedream or spends credits.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_PATH = str(ROOT / "app.py")


def make_analysis(*, questions: bool = False) -> dict[str, Any]:
    qs = (
        [
            {
                "id": "q1",
                "prompt": "What era is the setting?",
                "options": [{"id": "a", "label": "Modern"}, {"id": "b", "label": "Feudal"}],
                "allow_other": True,
            }
        ]
        if questions
        else []
    )
    return {
        "summary": "Two rivals duel on a rooftop.",
        "characters": [
            {
                "name": "Kaito",
                "role": "lead",
                "visual_guess": "red jacket",
                "suggested_ref": None,
                "confidence": 0.9,
            }
        ],
        "beats": ["standoff"],
        "tone": "tense",
        "panel_density": "cinematic",
        "aesthetic": "jjk_inspired",
        "confidence": 0.9,
        "risks": [],
        "first_five_focus": "the standoff",
        "brief": {
            "aesthetic": "jjk_inspired",
            "tone": "tense",
            "panel_density": "cinematic",
            "character_maps": [{"name": "Kaito", "ref": None, "look": "red jacket"}],
            "world": "rooftop",
            "do_not": [],
        },
        "questions": qs,
        "ready": not qs,
    }


def write_png(path: Path) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (40, 40, 40)).save(path, format="PNG")
    return path


def make_panel(run_dir: Path, index: int) -> dict[str, Any]:
    img = write_png(run_dir / "panels" / f"panel_{index:03d}.png")
    return {
        "id": f"p{index}",
        "index": index,
        "page": 1,
        "shot_type": "medium",
        "subject": "Kaito",
        "action": f"beat {index}",
        "emotion": "tense",
        "dialogue": f"line {index}",
        "setting": "rooftop",
        "continuity": "",
        "characters": ["Kaito"],
        "path": str(img),
        "prompt": "mock prompt",
        "negative_prompt": "",
        "critique": {"pass": True, "score": 1.0, "issues": [], "rewrite_notes": ""},
        "passed": True,
        "needs_review": False,
        "attempt": 0,
    }


class Harness:
    """Bundles the patched run dir so tests can inspect outputs."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir


@pytest.fixture
def patched_app(tmp_path, monkeypatch):
    """Patch every pipeline entry point app.py uses, before AppTest runs it."""
    import pipeline.analyze as analyze_mod
    import pipeline.export as export_mod
    import pipeline.run as run_mod
    import pipeline.style_library as lib_mod
    import pipeline.util as util_mod

    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("MANGA_MOCK_IMAGES", "1")

    run_dir = tmp_path / "run"
    (run_dir / "panels").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(util_mod, "new_run_dir", lambda: run_dir)
    monkeypatch.setattr(lib_mod, "save_character_map", lambda maps: None)
    monkeypatch.setattr(
        analyze_mod, "analyze_transcript", lambda router, transcript, aesthetic: make_analysis()
    )
    monkeypatch.setattr(
        analyze_mod, "apply_answers", lambda router, analysis, answers: make_analysis()
    )

    def fake_generate_batch(router, settings, bible, transcript, rdir, *, start_index=1, count=5, existing_panels=None, emit=None):
        panels = [make_panel(Path(rdir), start_index + i) for i in range(count)]
        if emit:
            emit("panels_planned", {"panels": panels})
        return {"panels": panels, "sequence": {"sequence_pass": True, "score": 1.0, "notes": ""}}

    def fake_regenerate_one(router, settings, bible, panel, rdir, *, edit_notes="", prior_notes=""):
        return make_panel(Path(rdir), int(panel["index"]))

    monkeypatch.setattr(run_mod, "generate_batch", fake_generate_batch)
    monkeypatch.setattr(run_mod, "regenerate_one", fake_regenerate_one)

    def fake_export_zip(rdir, panels):
        z = Path(rdir) / "storyboard.zip"
        z.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        return z

    monkeypatch.setattr(export_mod, "export_zip", fake_export_zip)

    return Harness(run_dir)
