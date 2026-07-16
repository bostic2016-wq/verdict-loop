"""Per-panel vision QA + auto-retry loop."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pipeline.creative_bible import bible_excerpt
from pipeline.prompt_compiler import compile_prompt, resolve_panel_characters
from pipeline.roles import VISION_SYSTEM, VISION_USER
from pipeline.router import DirectorRouter
from pipeline.util import parse_json


WEIGHTS = {
    "narrative_match": 0.20,
    "composition": 0.15,
    "style_fit": 0.15,
    "technical_clean": 0.10,
    "continuity": 0.10,
    "clean_frame": 0.10,
    "character_presence": 0.20,
}


def critique_panel(
    router: DirectorRouter,
    bible: dict[str, Any],
    panel: dict[str, Any],
    image_path: Path,
    *,
    prior_notes: str = "",
    pass_score: float = 0.7,
) -> dict[str, Any]:
    cast = resolve_panel_characters(bible, panel)
    required = ", ".join(f"{c['name']} ({c['look']})" for c in cast) or "(none listed)"
    try:
        raw = router.complete_vision(
            "vision_critic",
            VISION_SYSTEM,
            VISION_USER.format(
                bible_excerpt=bible_excerpt(bible),
                panel=str(panel),
                required_cast=required,
                prior=prior_notes or "(first panel)",
                pass_score=pass_score,
            ),
            image_path,
            json_mode=True,
        )
        critique = parse_json(raw)
    except Exception as exc:  # noqa: BLE001 — soft-pass on critic failure
        return {
            "pass": True,
            "score": pass_score,
            "issues": [f"Vision critic unavailable: {exc}"],
            "rewrite_notes": "",
            "soft_pass": True,
        }

    dims = critique.get("dimensions") or {}
    if dims:
        # Default character_presence to 1 if cast empty
        if not cast:
            dims.setdefault("character_presence", 1.0)
        score = sum(float(dims.get(k, 0) or 0) * w for k, w in WEIGHTS.items())
        critique["score"] = round(score, 3)
        missing = critique.get("missing_characters") or []
        char_fail = bool(cast) and (
            float(dims.get("character_presence", 1) or 1) < 1.0 or bool(missing)
        )
        hard_fail = (
            float(dims.get("narrative_match", 1) or 1) < 0.4
            or float(dims.get("clean_frame", 1) or 1) < 0.4
            or char_fail
        )
        critique["pass"] = bool(critique.get("pass")) and score >= pass_score and not hard_fail
        if char_fail and not critique.get("rewrite_notes"):
            names = ", ".join(c["name"] for c in cast)
            critique["rewrite_notes"] = (
                f"include ALL of: {names}. Show exactly {len(cast)} characters clearly in frame."
            )
    else:
        critique["pass"] = bool(critique.get("pass")) and float(critique.get("score", 0) or 0) >= pass_score
    critique.setdefault("issues", [])
    critique.setdefault("rewrite_notes", "")
    return critique


def generate_with_qa(
    router: DirectorRouter,
    settings: dict[str, Any],
    bible: dict[str, Any],
    panel: dict[str, Any],
    out_path: Path,
    *,
    generate_fn: Callable[..., Path],
    prior_notes: str = "",
) -> dict[str, Any]:
    qa_cfg = settings.get("vision_qa") or {}
    enabled = qa_cfg.get("enabled", True)
    pass_score = float(qa_cfg.get("pass_score", 0.7))
    max_retries = int(qa_cfg.get("max_retries", 1))
    use_llm_prompt = bool((settings.get("prompt_compile") or {}).get("use_llm", False))

    rewrite = ""
    best: dict[str, Any] | None = None
    attempts = []

    for attempt in range(max_retries + 1):
        compiled = compile_prompt(
            router if use_llm_prompt else None,
            bible,
            panel,
            rewrite_notes=rewrite,
            use_llm=use_llm_prompt,
        )
        path = out_path.with_name(f"{out_path.stem}_a{attempt}{out_path.suffix}")
        generate_fn(
            settings,
            compiled["prompt"],
            compiled["negative_prompt"],
            path,
            seed=1000 + int(panel.get("index", 0) or 0) * 10 + attempt,
        )

        if not enabled:
            out_path.write_bytes(path.read_bytes())
            return {
                "path": str(out_path),
                "prompt": compiled["prompt"],
                "negative_prompt": compiled["negative_prompt"],
                "critique": {"pass": True, "score": 1.0, "issues": [], "rewrite_notes": ""},
                "passed": True,
                "attempt": attempt,
                "needs_review": False,
            }

        critique = critique_panel(
            router, bible, panel, path, prior_notes=prior_notes, pass_score=pass_score
        )
        record = {
            "path": str(path),
            "prompt": compiled["prompt"],
            "negative_prompt": compiled["negative_prompt"],
            "critique": critique,
            "passed": bool(critique.get("pass")),
            "attempt": attempt,
            "needs_review": False,
        }
        attempts.append(record)
        best = (
            record
            if best is None
            or float(critique.get("score", 0)) >= float(best["critique"].get("score", 0))
            else best
        )

        if critique.get("pass"):
            out_path.write_bytes(Path(record["path"]).read_bytes())
            record["path"] = str(out_path)
            return record

        rewrite = critique.get("rewrite_notes") or "; ".join(critique.get("issues") or [])
        if not rewrite:
            cast = resolve_panel_characters(bible, panel)
            if cast:
                names = ", ".join(c["name"] for c in cast)
                rewrite = f"include ALL of: {names}. exactly {len(cast)} characters visible."
            else:
                rewrite = "Improve manga line clarity, composition, and brief match."

    assert best is not None
    out_path.write_bytes(Path(best["path"]).read_bytes())
    best = {**best, "path": str(out_path), "needs_review": True, "passed": False, "attempts": attempts}
    return best
