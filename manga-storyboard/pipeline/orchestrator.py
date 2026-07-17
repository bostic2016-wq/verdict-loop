"""Correct-loop orchestrator: script + refs in → generate → QA → fix → regenerate once.

Input script is structured JSON:

{
  "title": "...",
  "style": {"aesthetic": "jjk_inspired", "color_mode": "full color", "world": "..."},
  "characters": [{"name": "Kaito", "look": "short black hair, red jacket", "ref": "kaito.png"}],
  "pages": [
    {"page": 1, "layout": "3 stacked panels, read right-to-left",
     "panels": [
       {"index": 1, "shot_type": "wide", "subject": "...", "action": "...",
        "dialogue": "...", "setting": "...", "characters": ["Kaito"]}
     ]}
  ]
}

A flat top-level "panels" list (no pages) is also accepted.

Output layout under --out:
  panels/panel_NNN.png        final image per panel
  panels/panel_NNN_aK.png     attempt K (a0 = first, a1 = post-fix regeneration)
  prompts/panel_NNN.json      compiled prompt / negative prompt / refs per attempt
  qa/panel_NNN.json           structured QA verdict(s)
  run.json                    overall summary
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from pipeline.creative_bible import build_bible
from pipeline.generate import generate_panel_image
from pipeline.router import DirectorRouter
from pipeline.util import save_json
from pipeline.vision_qa import generate_with_qa

Emit = Callable[[str, dict[str, Any]], None]

REF_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class ScriptError(ValueError):
    pass


def load_script(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScriptError(f"Script is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ScriptError("Script root must be a JSON object")
    panels = flatten_panels(data)
    if not panels:
        raise ScriptError("Script has no panels (expected 'pages[].panels' or 'panels')")
    return data


def flatten_panels(script: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered panel list; assigns ids/indexes and carries page + layout."""
    panels: list[dict[str, Any]] = []
    pages = script.get("pages")
    if isinstance(pages, list) and pages:
        for page in pages:
            layout = page.get("layout") or ""
            for p in page.get("panels") or []:
                panels.append({**p, "page": page.get("page"), "page_layout": layout})
    else:
        panels = [dict(p) for p in (script.get("panels") or [])]
    for i, p in enumerate(panels):
        p.setdefault("index", i + 1)
        p.setdefault("id", f"p{p['index']}")
        p.setdefault("shot_type", "medium")
    return panels


def resolve_refs(script: dict[str, Any], refs_dir: Path | None) -> list[dict[str, Any]]:
    """Attach absolute ref image paths from the refs folder to script characters.

    Match priority: explicit 'ref' filename in the script, then a file whose
    stem equals the character name (case/space-insensitive).
    """
    files: dict[str, Path] = {}
    if refs_dir and Path(refs_dir).is_dir():
        for f in sorted(Path(refs_dir).iterdir()):
            if f.suffix.lower() in REF_SUFFIXES:
                files[f.name.lower()] = f
                files.setdefault(f.stem.lower().replace(" ", "_"), f)
                files.setdefault(f.stem.lower(), f)

    characters = []
    for c in script.get("characters") or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        ref_path = None
        ref = (c.get("ref") or "").strip().lower()
        if ref and ref in files:
            ref_path = files[ref]
        else:
            key = name.lower()
            ref_path = files.get(key) or files.get(key.replace(" ", "_"))
        characters.append(
            {
                "name": name,
                "look": c.get("look") or "",
                "ref": c.get("ref"),
                "ref_path": str(ref_path) if ref_path else None,
            }
        )
    return characters


def build_script_bible(script: dict[str, Any], refs_dir: Path | None) -> dict[str, Any]:
    style = script.get("style") or {}
    brief = {
        "aesthetic": style.get("aesthetic") or "jjk_inspired",
        "color_mode": style.get("color_mode") or "full color",
        "world": style.get("world") or "",
        "tone": style.get("tone") or "",
        "character_maps": [],
        "do_not": list(style.get("do_not") or []),
    }
    bible = build_bible(brief, aesthetic=brief["aesthetic"])
    # Replace library-derived characters with the script's own cast + folder refs
    bible["characters"] = resolve_refs(script, refs_dir)
    if style.get("notes"):
        bible["world"] = f"{bible.get('world', '')} {style['notes']}".strip()
    return bible


def run_correct_loop(
    script_path: Path,
    refs_dir: Path | None,
    out_dir: Path,
    settings: dict[str, Any],
    *,
    emit: Emit = lambda e, p: None,
) -> dict[str, Any]:
    """Generate every panel, QA it, and on failure apply the critic's
    suggested prompt fix and regenerate exactly once."""
    script = load_script(Path(script_path))
    panels = flatten_panels(script)
    bible = build_script_bible(script, refs_dir)

    out_dir = Path(out_dir)
    for sub in ("panels", "prompts", "qa"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    save_json(out_dir / "bible.json", bible)

    # Exactly one fix-and-regenerate per panel; no silent backend fallback.
    # Mock mode skips vision QA (placeholder images can never conform).
    from pipeline.config import is_mock

    settings = {**settings}
    settings["vision_qa"] = {
        **(settings.get("vision_qa") or {}),
        "enabled": not is_mock(),
        "max_retries": 1,
    }
    settings.setdefault("generation", {})["strict"] = True

    router = DirectorRouter(settings, run_dir=out_dir)
    results: list[dict[str, Any]] = []
    prior_notes = ""
    for panel in panels:
        idx = int(panel["index"])
        emit("panel_start", {"index": idx, "panel": panel})
        out_path = out_dir / "panels" / f"panel_{idx:03d}.png"
        record = generate_with_qa(
            router,
            settings,
            bible,
            panel,
            out_path,
            generate_fn=generate_panel_image,
            prior_notes=prior_notes,
        )
        merged = {**panel, **record}
        results.append(merged)

        attempts = record.get("attempts") or [record]
        save_json(
            out_dir / "prompts" / f"panel_{idx:03d}.json",
            [
                {
                    "attempt": a.get("attempt"),
                    "prompt": a.get("prompt"),
                    "negative_prompt": a.get("negative_prompt"),
                    "path": a.get("path"),
                }
                for a in attempts
            ],
        )
        save_json(
            out_dir / "qa" / f"panel_{idx:03d}.json",
            {
                "passed": record.get("passed"),
                "needs_review": record.get("needs_review"),
                "final_verdict": record.get("critique"),
                "attempts": [
                    {"attempt": a.get("attempt"), "verdict": a.get("critique")} for a in attempts
                ],
            },
        )
        prior_notes = f"{panel.get('shot_type')}: {panel.get('action')} | {panel.get('continuity', '')}"
        emit("panel_done", {"index": idx, "record": merged})

    passed = [r for r in results if r.get("passed")]
    summary = {
        "title": script.get("title") or Path(script_path).stem,
        "script": str(script_path),
        "refs_dir": str(refs_dir) if refs_dir else None,
        "panel_count": len(results),
        "passed": len(passed),
        "failed": len(results) - len(passed),
        "failed_panels": [int(r["index"]) for r in results if not r.get("passed")],
        "panels": [
            {
                "index": r.get("index"),
                "path": r.get("path"),
                "passed": r.get("passed"),
                "needs_review": r.get("needs_review", False),
                "issues": (r.get("critique") or {}).get("issues") or [],
                "suggested_prompt_fix": (r.get("critique") or {}).get("suggested_prompt_fix") or "",
            }
            for r in results
        ],
    }
    save_json(out_dir / "run.json", summary)
    return summary
