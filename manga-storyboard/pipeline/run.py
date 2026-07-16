"""Orchestrate a storyboard run: plan → generate → QA → sequence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pipeline.generate import generate_panel_image
from pipeline.panel_grammar import plan_panels
from pipeline.router import DirectorRouter
from pipeline.sequence_qa import critique_sequence
from pipeline.util import save_json
from pipeline.vision_qa import generate_with_qa


Emit = Callable[[str, dict[str, Any]], None]


def _noop(event: str, payload: dict[str, Any]) -> None:
    return None


def generate_batch(
    router: DirectorRouter,
    settings: dict[str, Any],
    bible: dict[str, Any],
    transcript: str,
    run_dir: Path,
    *,
    start_index: int = 1,
    count: int = 5,
    existing_panels: list[dict[str, Any]] | None = None,
    emit: Emit = _noop,
) -> dict[str, Any]:
    panels = existing_panels or plan_panels(
        router, bible, transcript, start_index=start_index, count=count
    )
    emit("panels_planned", {"panels": panels})

    results: list[dict[str, Any]] = []
    prior_notes = ""
    for panel in panels:
        emit("panel_start", {"index": panel.get("index"), "panel": panel})
        out = run_dir / "panels" / f"panel_{panel['index']:03d}.png"
        record = generate_with_qa(
            router,
            settings,
            bible,
            panel,
            out,
            generate_fn=generate_panel_image,
            prior_notes=prior_notes,
        )
        try:
            from pipeline.tokens import record_image

            record_image(run_dir, 1)
        except Exception:  # noqa: BLE001
            pass
        merged = {**panel, **record}
        results.append(merged)
        prior_notes = f"{panel.get('shot_type')}: {panel.get('action')} | {panel.get('continuity', '')}"
        emit("panel_done", {"index": panel.get("index"), "record": merged})

    seq_cfg = settings.get("sequence_qa") or {}
    sequence: dict[str, Any] = {"sequence_pass": True, "panels_to_regen": [], "notes": ""}
    # Sequence critique is optional; auto-regen is OFF by default (major slowdown on "next 5")
    if seq_cfg.get("enabled", False) and results:
        paths = [Path(r["path"]) for r in results]
        sequence = critique_sequence(
            router,
            bible,
            panels,
            paths,
            pass_score=float(seq_cfg.get("pass_score", 0.7)),
        )
        emit("sequence_done", {"sequence": sequence})

        if seq_cfg.get("regen_on_fail", False):
            for idx in sequence.get("panels_to_regen") or []:
                try:
                    i = int(idx) - 1
                except (TypeError, ValueError):
                    continue
                if i < 0 or i >= len(results):
                    continue
                panel = panels[i]
                emit("panel_regen_sequence", {"index": panel.get("index")})
                out = run_dir / "panels" / f"panel_{panel['index']:03d}.png"
                prior = ""
                if i > 0:
                    prev = panels[i - 1]
                    prior = f"{prev.get('shot_type')}: {prev.get('action')}"
                record = generate_with_qa(
                    router,
                    settings,
                    bible,
                    panel,
                    out,
                    generate_fn=generate_panel_image,
                    prior_notes=prior,
                )
                results[i] = {**panel, **record}

    payload = {"panels": results, "sequence": sequence}
    save_json(run_dir / f"batch_{start_index:03d}.json", payload)
    return payload


def regenerate_one(
    router: DirectorRouter,
    settings: dict[str, Any],
    bible: dict[str, Any],
    panel: dict[str, Any],
    run_dir: Path,
    *,
    edit_notes: str = "",
    prior_notes: str = "",
) -> dict[str, Any]:
    if edit_notes:
        panel = {**panel, "notes": f"{panel.get('notes', '')} | {edit_notes}".strip(" |")}
        # Fold into action for prompt compiler
        panel["action"] = f"{panel.get('action', '')}. Director note: {edit_notes}"
    out = run_dir / "panels" / f"panel_{panel['index']:03d}.png"
    record = generate_with_qa(
        router,
        settings,
        bible,
        panel,
        out,
        generate_fn=generate_panel_image,
        prior_notes=prior_notes,
    )
    return {**panel, **record}
