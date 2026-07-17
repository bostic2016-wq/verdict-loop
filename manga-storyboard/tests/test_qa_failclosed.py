"""Unit tests for the fail-closed conformance QA and the single-retry loop."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.vision_qa import CHECK_KEYS, _normalize_verdict, critique_panel, generate_with_qa

BIBLE = {"characters": [], "do_not": [], "aesthetic_name": "test", "tone": "tense"}
PANEL = {"index": 1, "shot_type": "wide", "subject": "duel", "action": "standoff", "characters": []}


class RaisingRouter:
    def complete_vision(self, *args, **kwargs):
        raise RuntimeError("critic down")


class CannedRouter:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    def complete_vision(self, *args, **kwargs):
        self.calls += 1
        return json.dumps(self.payload)


def _all_ok_verdict(**overrides) -> dict:
    v = {
        "pass": True,
        "checks": {k: {"ok": True, "notes": ""} for k in CHECK_KEYS},
        "visible_characters": [],
        "missing_characters": [],
        "notes": "conforms",
        "suggested_prompt_fix": "",
    }
    v.update(overrides)
    return v


def test_critic_unavailable_fails_closed(tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    verdict = critique_panel(RaisingRouter(), BIBLE, PANEL, img)
    assert verdict["pass"] is False
    assert all(not c["ok"] for c in verdict["checks"].values())


def test_missing_check_fails_closed():
    raw = _all_ok_verdict()
    del raw["checks"]["reading_order"]
    verdict = _normalize_verdict(raw, [])
    assert verdict["pass"] is False
    assert verdict["checks"]["reading_order"]["ok"] is False


def test_uncertain_check_fails_even_if_critic_says_pass():
    raw = _all_ok_verdict()
    raw["checks"]["text_and_bubbles"] = {"ok": False, "notes": "cannot read the bubble"}
    verdict = _normalize_verdict(raw, ["Kaito"])
    assert verdict["pass"] is False
    assert "text_and_bubbles" in verdict["issues"][0]
    assert "Kaito" in verdict["suggested_prompt_fix"]


def test_missing_characters_override_ok_check():
    raw = _all_ok_verdict(missing_characters=["Ren"])
    verdict = _normalize_verdict(raw, ["Kaito", "Ren"])
    assert verdict["pass"] is False
    assert verdict["checks"]["character_consistency"]["ok"] is False


def test_all_checks_ok_passes():
    verdict = _normalize_verdict(_all_ok_verdict(), ["Kaito"])
    assert verdict["pass"] is True
    assert verdict["score"] == 1.0


def test_loop_applies_fix_and_regenerates_exactly_once(tmp_path):
    failing = _all_ok_verdict(**{"pass": False, "suggested_prompt_fix": "make Kaito face camera"})
    failing["checks"]["scene_match"] = {"ok": False, "notes": "wrong action"}
    router = CannedRouter(failing)

    generated: list[str] = []

    def fake_generate(settings, prompt, negative, out_path, **kwargs):
        generated.append(prompt)
        Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\n")
        return out_path

    settings = {"vision_qa": {"enabled": True, "max_retries": 1}, "prompt_compile": {"use_llm": False}}
    record = generate_with_qa(
        router, settings, BIBLE, PANEL, tmp_path / "panel_001.png", generate_fn=fake_generate
    )

    assert len(generated) == 2, "must regenerate exactly once after a QA failure"
    assert router.calls == 2
    assert generated[1].startswith("make Kaito face camera"), "suggested fix must lead the retry prompt"
    assert record["passed"] is False and record["needs_review"] is True
    assert (tmp_path / "panel_001.png").exists()
    assert (tmp_path / "panel_001_a0.png").exists() and (tmp_path / "panel_001_a1.png").exists()
