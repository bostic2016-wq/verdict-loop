"""Compile panel briefs into image prompts using bible + style preset."""

from __future__ import annotations

import re
from typing import Any

from pipeline.roles import PROMPT_SYSTEM
from pipeline.router import DirectorRouter
from pipeline.util import parse_json


def _bible_char(bible: dict[str, Any], name: str) -> dict[str, Any] | None:
    key = (name or "").strip().lower()
    for c in bible.get("characters") or []:
        if (c.get("name") or "").strip().lower() == key:
            return c
    # partial match (e.g. "King Edward" vs "Edward")
    for c in bible.get("characters") or []:
        cn = (c.get("name") or "").strip().lower()
        if key and (key in cn or cn in key):
            return c
    return None


def resolve_panel_characters(bible: dict[str, Any], panel: dict[str, Any]) -> list[dict[str, Any]]:
    """Build ordered character list that MUST appear in the panel (with ref image paths)."""
    from pipeline.style_library import resolve_ref_path

    names = list(panel.get("characters") or [])
    # Also pull names mentioned in subject/action/dialogue that exist in the bible
    blob = " ".join(
        str(panel.get(k) or "") for k in ("subject", "action", "dialogue", "notes", "continuity")
    )
    for c in bible.get("characters") or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        if re.search(rf"\b{re.escape(name)}\b", blob, flags=re.IGNORECASE):
            if not any(n.lower() == name.lower() for n in names):
                names.append(name)

    resolved = []
    seen = set()
    for name in names:
        key = name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        match = _bible_char(bible, name)
        look = (match.get("look") if match else "") or "distinct manga character"
        ref = match.get("ref") if match else None
        ref_path = resolve_ref_path(ref) or resolve_ref_path(name)
        resolved.append(
            {
                "name": match.get("name") if match else name,
                "look": look,
                "ref_path": str(ref_path) if ref_path else None,
            }
        )
    return resolved


def collect_reference_paths(cast: list[dict[str, Any]]) -> list[Any]:
    """Ordered, deduped ref image paths for this panel's cast."""
    from pathlib import Path

    out: list[Path] = []
    seen: set[str] = set()
    for c in cast:
        rp = c.get("ref_path")
        if rp and rp not in seen:
            seen.add(rp)
            path = Path(rp)
            if path.exists():
                out.append(path)
    return out


def compile_prompt_local(bible: dict[str, Any], panel: dict[str, Any]) -> dict[str, Any]:
    """Deterministic compiler — prioritizes full character cast visibility + ref binding."""
    cast = resolve_panel_characters(bible, panel)
    n = len(cast)

    # Bind each reference image (in payload order) to its character by name
    ref_lines = []
    ref_idx = 0
    for c in cast:
        if c.get("ref_path"):
            ref_idx += 1
            ref_lines.append(
                f"reference image {ref_idx} is {c['name']} — draw {c['name']} with EXACTLY this "
                f"character design: same face, same hairstyle, same outfit, same proportions"
            )
    ref_block = ". ".join(ref_lines)

    if n == 0:
        cast_block = "characters as implied by the scene"
        count_line = "show the correct cast for this beat"
    elif n == 1:
        c = cast[0]
        cast_block = f"ONLY {c['name']} visible ({c['look']})"
        count_line = f"exactly 1 character in frame: {c['name']}"
    else:
        cast_block = "; ".join(f"{c['name']} ({c['look']})" for c in cast)
        names = ", ".join(c["name"] for c in cast)
        count_line = (
            f"CRITICAL: exactly {n} characters MUST all be clearly visible together in this panel: {names}. "
            f"Do not omit any of them. Do not add extra people."
        )

    positive_parts = [
        (bible.get("style_positive") or "").replace("\n", " ").strip(),
        "single manga panel, no collage, no comic page layout, no borders",
        count_line,
        ref_block,
        f"required cast: {cast_block}",
        f"shot: {panel.get('shot_type', 'medium')}",
        f"subject: {panel.get('subject', '')}",
        f"action: {panel.get('action', '')}",
        f"emotion: {panel.get('emotion', '')}",
        f"setting: {panel.get('setting', '')}",
        f"continuity: {panel.get('continuity', '')}",
        "readable silhouettes, clear figure separation, full faces visible when multiple characters",
    ]
    positive = ", ".join(p for p in positive_parts if p)

    negatives = ", ".join(
        p
        for p in [
            (bible.get("style_negative") or "").replace("\n", " ").strip(),
            ", ".join(bible.get("do_not") or []),
            "missing character",
            "one character only when multiple required",
            "crowd of extras",
            "faceless blobs",
            "cropped out main character",
        ]
        if p
    )
    return {
        "prompt": positive,
        "negative_prompt": negatives,
        "reference_paths": [str(p) for p in collect_reference_paths(cast)],
    }


def compile_prompt(
    router: DirectorRouter | None,
    bible: dict[str, Any],
    panel: dict[str, Any],
    *,
    rewrite_notes: str = "",
    use_llm: bool = False,
) -> dict[str, str]:
    local = compile_prompt_local(bible, panel)
    if rewrite_notes:
        # Character-fix rewrites go first so the model prioritizes cast
        local["prompt"] = f"{rewrite_notes}. {local['prompt']}"

    if not use_llm or router is None:
        return local

    reference_paths = local.get("reference_paths") or []

    import json

    cast = resolve_panel_characters(bible, panel)
    try:
        raw = router.complete(
            "director",
            PROMPT_SYSTEM,
            (
                f"Bible characters:\n{json.dumps(bible.get('characters') or [], indent=2)[:3000]}\n\n"
                f"Panel:\n{json.dumps(panel, indent=2)}\n\n"
                f"REQUIRED cast (all must appear): {json.dumps(cast)}\n"
                f"Rewrite notes: {rewrite_notes or 'none'}\n\n"
                f"Seed prompt:\n{local['prompt']}\n\n"
                "Return JSON with prompt + negative_prompt. "
                "The prompt MUST explicitly name every required character and their look, "
                "and state the exact character count."
            ),
            json_mode=True,
            temperature=0.2,
        )
        data = parse_json(raw)
        prompt = data.get("prompt") or local["prompt"]
        # Safety: re-append cast count if LLM dropped it
        if cast and str(len(cast)) not in prompt and "exactly" not in prompt.lower():
            names = ", ".join(c["name"] for c in cast)
            prompt = f"exactly {len(cast)} characters visible: {names}. {prompt}"
        return {
            "prompt": prompt,
            "negative_prompt": data.get("negative_prompt") or local["negative_prompt"],
            "reference_paths": reference_paths,
        }
    except Exception:  # noqa: BLE001
        return local
