"""Creative bible — locked editorial document for a run."""

from __future__ import annotations

from typing import Any

from pipeline.util import load_style


def build_bible(
    brief: dict[str, Any],
    *,
    aesthetic: str | None = None,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aesthetic_id = aesthetic or brief.get("aesthetic") or "jjk_inspired"
    try:
        style = load_style(aesthetic_id)
    except FileNotFoundError:
        style = load_style("jjk_inspired")
        aesthetic_id = "jjk_inspired"

    characters = []
    for row in brief.get("character_maps") or []:
        characters.append(
            {
                "name": row.get("name", "Unknown"),
                "look": row.get("look", ""),
                "ref": row.get("ref"),
            }
        )
    if not characters and analysis:
        for c in analysis.get("characters") or []:
            characters.append(
                {
                    "name": c.get("name", "Unknown"),
                    "look": c.get("visual_guess", ""),
                    "ref": c.get("suggested_ref"),
                }
            )

    # Fill any missing looks/refs from the persistent character library
    try:
        from pipeline.style_library import merge_saved_characters

        characters = merge_saved_characters(characters)
    except Exception:  # noqa: BLE001 — library optional
        pass

    do_not = list(brief.get("do_not") or [])
    for required in ("photoreal", "speech bubbles in image", "watermarks", "extra unasked text"):
        if required not in do_not:
            do_not.append(required)

    return {
        "aesthetic": aesthetic_id,
        "aesthetic_name": style.get("name", aesthetic_id),
        "style_positive": (style.get("positive_tags") or "").strip(),
        "style_negative": (style.get("negative_tags") or "").strip(),
        "style_power": (style.get("power_tags") or "").strip(),
        "color_mode": brief.get("color_mode") or "full color",
        "style_settings": style.get("settings") or {},
        "framing_hints": style.get("framing_hints") or [],
        "tone": brief.get("tone") or (analysis or {}).get("tone") or "",
        "panel_density": brief.get("panel_density") or "cinematic",
        "world": brief.get("world") or "",
        "characters": characters,
        "do_not": do_not,
        "continuity_anchors": brief.get("continuity_anchors") or [],
        "first_five_focus": (analysis or {}).get("first_five_focus") or "",
    }


def bible_excerpt(bible: dict[str, Any], max_chars: int = 2500) -> str:
    import json

    slim = {
        "aesthetic": bible.get("aesthetic_name"),
        "tone": bible.get("tone"),
        "panel_density": bible.get("panel_density"),
        "world": bible.get("world"),
        "characters": bible.get("characters"),
        "do_not": bible.get("do_not"),
        "continuity_anchors": bible.get("continuity_anchors"),
    }
    text = json.dumps(slim, indent=2, ensure_ascii=False)
    return text[:max_chars]
