"""Compile panel briefs into image prompts using bible + style preset."""

from __future__ import annotations

from typing import Any

from pipeline.roles import PROMPT_SYSTEM
from pipeline.router import DirectorRouter
from pipeline.util import parse_json


def compile_prompt_local(bible: dict[str, Any], panel: dict[str, Any]) -> dict[str, str]:
    """Deterministic fallback compiler (no LLM)."""
    chars = panel.get("characters") or []
    char_lines = []
    for name in chars:
        match = next((c for c in (bible.get("characters") or []) if c.get("name") == name), None)
        if match:
            char_lines.append(f"{name}: {match.get('look') or 'as established'}")
        else:
            char_lines.append(str(name))

    positive = ", ".join(
        part
        for part in [
            (bible.get("style_positive") or "").replace("\n", " ").strip(),
            f"shot: {panel.get('shot_type', 'medium')}",
            f"subject: {panel.get('subject', '')}",
            f"action: {panel.get('action', '')}",
            f"emotion: {panel.get('emotion', '')}",
            f"setting: {panel.get('setting', '')}",
            f"characters: {'; '.join(char_lines)}" if char_lines else "",
            f"continuity: {panel.get('continuity', '')}",
            "single manga panel, no collage, no borders",
        ]
        if part
    )

    negatives = ", ".join(
        part
        for part in [
            (bible.get("style_negative") or "").replace("\n", " ").strip(),
            ", ".join(bible.get("do_not") or []),
        ]
        if part
    )
    return {"prompt": positive, "negative_prompt": negatives}


def compile_prompt(
    router: DirectorRouter | None,
    bible: dict[str, Any],
    panel: dict[str, Any],
    *,
    rewrite_notes: str = "",
) -> dict[str, str]:
    local = compile_prompt_local(bible, panel)
    if rewrite_notes:
        local["prompt"] = f"{local['prompt']}. FIX: {rewrite_notes}"

    if router is None:
        return local

    import json

    try:
        raw = router.complete(
            "director",
            PROMPT_SYSTEM,
            (
                f"Bible:\n{json.dumps({k: bible[k] for k in ('aesthetic_name','tone','characters','do_not','style_positive','style_negative') if k in bible}, indent=2)[:4000]}\n\n"
                f"Panel:\n{json.dumps(panel, indent=2)}\n\n"
                f"Rewrite notes: {rewrite_notes or 'none'}\n\n"
                f"Seed prompt (improve, keep manga tags):\n{local['prompt']}"
            ),
            json_mode=True,
            temperature=0.3,
        )
        data = parse_json(raw)
        return {
            "prompt": data.get("prompt") or local["prompt"],
            "negative_prompt": data.get("negative_prompt") or local["negative_prompt"],
        }
    except Exception:  # noqa: BLE001
        return local
