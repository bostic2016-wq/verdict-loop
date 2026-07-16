from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from harness.config import load_settings, require_text_keys
from harness.creative_loop import run_creative
from harness.images import ImageClient
from harness.loop import run_debate
from harness.mock_router import MockRouter
from harness.money import attach_money_context
from harness.research import merge_user_context
from harness.router import ModelRouter


ProgressCb = Callable[[str, dict[str, Any]], None]


def _new_run_dir(root: Path, outputs_dir: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    path = root / outputs_dir / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_pipeline(
    claim: str,
    *,
    with_images: bool = False,
    dry_run: bool = False,
    extra_context: str | None = None,
    config_path: Path | None = None,
    on_progress: ProgressCb | None = None,
    detail: str = "brief",
) -> dict[str, Any]:
    settings = load_settings(config_path)
    if not dry_run:
        require_text_keys(settings)
    root: Path = settings["_root"]
    outputs_dir = settings.get("paths", {}).get("outputs_dir", "outputs/runs")
    run_dir = _new_run_dir(root, outputs_dir)

    detail = (detail or "brief").lower()
    if detail not in {"brief", "detailed"}:
        detail = "brief"

    router: ModelRouter | MockRouter = (
        MockRouter(settings) if dry_run else ModelRouter(settings)
    )
    claim = merge_user_context(claim, extra_context)
    claim, money_facts = attach_money_context(claim)
    partial: dict[str, Any] = {
        "run_dir": str(run_dir),
        "claim": claim,
        "detail": detail,
        "mode": "single",
        "money_facts": money_facts if money_facts.get("has_money_signal") else None,
        "debate": None,
        "creative": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    }

    def emit(event: str, payload: dict[str, Any]) -> None:
        if event in {"scout_done", "advocate_done", "skeptic_done", "judge_done"}:
            partial.setdefault("_events", []).append({"event": event, **payload})
            _save_partial(run_dir, partial)
        if on_progress:
            on_progress(event, payload)

    emit("run_start", {"run_dir": str(run_dir), "claim": claim, "detail": detail})

    try:
        debate = run_debate(
            claim, router, settings, on_progress=emit, detail=detail
        )
        partial["debate"] = debate

        creative_cfg = settings.get("creative", {})
        recommendation = str(debate["verdict"].get("recommendation", "")).lower()
        allow_on_reject = bool(creative_cfg.get("generate_on_reject", True))
        creative_enabled = bool(creative_cfg.get("enabled", True)) and with_images
        if recommendation == "dont" and not allow_on_reject:
            creative_enabled = False

        creative_result: dict[str, Any] | None = None
        if creative_enabled:
            image_client = ImageClient(settings, dry_run=dry_run)
            creative_result = run_creative(
                claim,
                debate["verdict"],
                router,
                image_client,
                settings,
                run_dir,
                on_progress=emit,
            )
        else:
            emit(
                "creative_skipped",
                {"reason": "disabled or rejected without generate_on_reject"},
            )

        partial["creative"] = creative_result
        partial["status"] = "complete"
        partial.pop("_events", None)
        (run_dir / "result.json").write_text(
            json.dumps(partial, indent=2), encoding="utf-8"
        )
        _write_markdown(run_dir, partial)
        emit("run_done", {"run_dir": str(run_dir)})
        return partial
    except Exception as exc:
        partial["status"] = "error"
        partial["error"] = str(exc)
        _save_partial(run_dir, partial)
        raise


def run_compare(
    claim_a: str,
    claim_b: str,
    *,
    dry_run: bool = False,
    config_path: Path | None = None,
    on_progress: ProgressCb | None = None,
    detail: str = "brief",
) -> dict[str, Any]:
    """Run two plans sequentially (images off) and pick a winner line."""
    settings = load_settings(config_path)
    if not dry_run:
        require_text_keys(settings)

    def tag(prefix: str) -> ProgressCb:
        def _cb(event: str, payload: dict[str, Any]) -> None:
            if on_progress:
                on_progress(f"{prefix}_{event}", payload)

        return _cb

    result_a = run_pipeline(
        claim_a,
        with_images=False,
        dry_run=dry_run,
        config_path=config_path,
        on_progress=tag("a"),
        detail=detail,
    )
    result_b = run_pipeline(
        claim_b,
        with_images=False,
        dry_run=dry_run,
        config_path=config_path,
        on_progress=tag("b"),
        detail=detail,
    )

    router: ModelRouter | MockRouter = (
        MockRouter(settings) if dry_run else ModelRouter(settings)
    )
    from harness.followup import pick_between_plans

    if dry_run:
        pick = (
            "Plan A and Plan B are close in this dry-run; "
            "prefer the clearer next step."
        )
    else:
        pick = pick_between_plans(router, result_a, result_b)

    compare: dict[str, Any] = {
        "mode": "compare",
        "detail": detail,
        "claim_a": claim_a,
        "claim_b": claim_b,
        "result_a": result_a,
        "result_b": result_b,
        "pick": pick,
        "run_dir": result_a.get("run_dir"),
        "status": "complete",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Persist pick next to plan A run for follow-ups
    try:
        run_dir = Path(result_a["run_dir"])
        (run_dir / "compare.json").write_text(
            json.dumps(
                {
                    "claim_a": claim_a,
                    "claim_b": claim_b,
                    "pick": pick,
                    "run_dir_b": result_b.get("run_dir"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return compare


def _save_partial(run_dir: Path, partial: dict[str, Any]) -> None:
    (run_dir / "partial.json").write_text(
        json.dumps(partial, indent=2, default=str), encoding="utf-8"
    )


def _write_markdown(run_dir: Path, result: dict[str, Any]) -> None:
    debate = result.get("debate") or {}
    verdict = debate.get("verdict") or {}
    lines = [
        "# Verdict Loop Report",
        "",
        f"**Claim:** {result['claim']}",
        f"**Detail:** {result.get('detail', 'brief')}",
        "",
        "## Bottom line",
        "",
        verdict.get("bottom_line") or verdict.get("reasoning") or "",
        "",
        "## Verdict",
        "",
        f"- Recommendation: **{verdict.get('recommendation')}**",
        f"- Score: {verdict.get('score')}",
        f"- Reasoning: {verdict.get('reasoning')}",
        "",
        "### Conditions",
    ]
    for c in verdict.get("conditions") or []:
        lines.append(f"- {c}")

    if result.get("detail") == "detailed":
        lines += ["", "## Research notes", ""]
        notes = debate.get("final_notes") or {}
        if notes:
            lines.append(f"**Summary:** {notes.get('summary', '')}")
            lines.append("")
            for label, key in (
                ("Supporting points", "supporting_points"),
                ("Risks", "risks"),
                ("Open questions", "open_questions"),
                ("Assumptions", "assumptions"),
            ):
                lines.append(f"### {label}")
                for item in notes.get(key) or []:
                    lines.append(f"- {item}")
                lines.append("")

        lines += ["## Debate rounds", ""]
        for rnd in debate.get("rounds") or []:
            j = rnd["judgment"]
            lines += [
                f"### Round {rnd['round']}",
                "",
                f"**Judge score:** {j.get('score')} — continue={j.get('continue')}",
                "",
                "#### Advocate",
                rnd["advocate"],
                "",
                "#### Skeptic",
                rnd["skeptic"],
                "",
            ]
    else:
        notes = debate.get("final_notes") or {}
        lines += [
            "",
            "## Brief notes",
            "",
            f"**Summary:** {notes.get('summary', '')}",
            "",
        ]

    creative = result.get("creative")
    if creative:
        promo = creative["promo"]
        lines += [
            "## Promo pack",
            "",
            f"**Headline:** {promo.get('headline')}",
            f"**Tagline:** {promo.get('tagline')}",
            "",
            promo.get("promo_blurb") or "",
            "",
            "### Images",
            "",
        ]
        for asset in creative.get("approved") or []:
            lines.append(
                f"- `{asset['path']}` — score {asset['critique'].get('score')} "
                f"(passed={asset['passed']})"
            )

    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
