"""Per-panel vision QA (fail-closed conformance verdict) + auto-retry loop.

The critic judges conformance to the source script and reference art — not
artistic taste. Every check must explicitly pass; a missing check, an uncertain
critic, or an unavailable critic all count as FAIL (never soft-pass).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pipeline.creative_bible import bible_excerpt
from pipeline.prompt_compiler import compile_prompt, panel_calls_for_power, resolve_panel_characters
from pipeline.roles import VISION_SYSTEM, VISION_USER
from pipeline.router import DirectorRouter
from pipeline.util import parse_json

CHECK_KEYS = (
    "panel_count_and_layout",
    "reading_order",
    "character_consistency",
    "scene_match",
    "text_and_bubbles",
    "anatomy_artifacts",
)


def _failed_verdict(reason: str) -> dict[str, Any]:
    return {
        "pass": False,
        "checks": {
            k: {"ok": False, "notes": reason} for k in CHECK_KEYS
        },
        "visible_characters": [],
        "missing_characters": [],
        "notes": reason,
        "suggested_prompt_fix": "",
        # Compatibility fields (Streamlit filmstrip / review card)
        "score": 0.0,
        "issues": [reason],
        "rewrite_notes": "",
    }


def _normalize_verdict(raw: dict[str, Any], required_names: list[str]) -> dict[str, Any]:
    """Fail-closed normalization: any absent or non-true check fails the verdict."""
    checks_in = raw.get("checks") or {}
    checks: dict[str, dict[str, Any]] = {}
    for key in CHECK_KEYS:
        c = checks_in.get(key)
        if not isinstance(c, dict):
            checks[key] = {"ok": False, "notes": "check missing from critic response"}
            continue
        checks[key] = {**c, "ok": c.get("ok") is True}

    missing = [str(m) for m in (raw.get("missing_characters") or [])]
    if missing and checks["character_consistency"]["ok"]:
        checks["character_consistency"] = {
            "ok": False,
            "notes": f"critic listed missing characters: {', '.join(missing)}",
        }

    ok_count = sum(1 for c in checks.values() if c["ok"])
    all_ok = ok_count == len(CHECK_KEYS)
    passed = bool(raw.get("pass")) and all_ok

    issues = [
        f"{key}: {checks[key].get('notes') or 'failed'}"
        for key in CHECK_KEYS
        if not checks[key]["ok"]
    ]
    fix = str(raw.get("suggested_prompt_fix") or "").strip()
    if not passed and not fix and required_names:
        fix = (
            f"include ALL of: {', '.join(required_names)}. "
            f"Show exactly {len(required_names)} characters clearly in frame."
        )

    return {
        "pass": passed,
        "checks": checks,
        "visible_characters": raw.get("visible_characters") or [],
        "missing_characters": missing,
        "notes": str(raw.get("notes") or ""),
        "suggested_prompt_fix": fix,
        # Compatibility fields
        "score": round(ok_count / len(CHECK_KEYS), 3),
        "issues": issues,
        "rewrite_notes": fix,
    }


def critique_panel(
    router: DirectorRouter,
    bible: dict[str, Any],
    panel: dict[str, Any],
    image_path: Path,
    *,
    prior_notes: str = "",
    pass_score: float = 0.7,  # kept for call compatibility; verdict is check-based
    reference_paths: list[Path] | None = None,
    expected_layout: str = "",
) -> dict[str, Any]:
    cast = resolve_panel_characters(bible, panel)
    required = ", ".join(f"{c['name']} ({c['look']})" for c in cast) or "(none listed)"
    required_names = [c["name"] for c in cast]
    refs = [Path(p) for p in (reference_paths or []) if Path(p).exists()][:3]
    user_msg = VISION_USER.format(
        bible_excerpt=bible_excerpt(bible),
        panel=str(panel),
        expected_layout=expected_layout
        or "exactly 1 panel (single illustration, no collage or page grid)",
        required_cast=required,
        power_expected="YES — the script calls for power/energy effects"
        if panel_calls_for_power(panel)
        else "NO — there must be NO energy auras or power effects in this panel",
        prior=prior_notes or "(first panel)",
    )
    if refs:
        ref_names = [c["name"] for c in cast if c.get("ref_path")]
        user_msg += (
            f"\n\nIMAGE 1 is the generated storyboard image. Images 2+ are the artist's OWN "
            f"reference drawings of: {', '.join(ref_names)}. Judge character_consistency against "
            f"these references — face, hairstyle, outfit must match. Off-model = ok false."
        )
    try:
        raw = router.complete_vision(
            "vision_critic",
            VISION_SYSTEM,
            user_msg,
            [image_path, *refs],
            json_mode=True,
        )
        data = parse_json(raw)
    except Exception as exc:  # noqa: BLE001 — fail closed, never soft-pass
        return _failed_verdict(f"Vision critic unavailable: {exc}")
    if not isinstance(data, dict):
        return _failed_verdict("Vision critic returned non-object JSON")
    return _normalize_verdict(data, required_names)


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
        ref_paths = [Path(p) for p in (compiled.get("reference_paths") or [])]
        path = out_path.with_name(f"{out_path.stem}_a{attempt}{out_path.suffix}")
        generate_fn(
            settings,
            compiled["prompt"],
            compiled["negative_prompt"],
            path,
            seed=1000 + int(panel.get("index", 0) or 0) * 10 + attempt,
            reference_paths=ref_paths,
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
            router,
            bible,
            panel,
            path,
            prior_notes=prior_notes,
            pass_score=pass_score,
            reference_paths=ref_paths,
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

        # Apply the critic's suggested prompt fix for the single regeneration
        rewrite = (
            critique.get("suggested_prompt_fix")
            or critique.get("rewrite_notes")
            or "; ".join(critique.get("issues") or [])
        )
        if not rewrite:
            cast = resolve_panel_characters(bible, panel)
            if cast:
                names = ", ".join(c["name"] for c in cast)
                rewrite = f"include ALL of: {names}. exactly {len(cast)} characters visible."
            else:
                rewrite = "Match the script beat exactly: correct action, setting, and cast."

    assert best is not None
    out_path.write_bytes(Path(best["path"]).read_bytes())
    best = {**best, "path": str(out_path), "needs_review": True, "passed": False, "attempts": attempts}
    return best
