from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from harness import roles
from harness.images import ImageClient
from harness.router import ModelRouter, parse_json


ProgressCb = Callable[[str, dict[str, Any]], None]


def run_creative(
    claim: str,
    verdict: dict[str, Any],
    router: ModelRouter,
    image_client: ImageClient,
    settings: dict[str, Any],
    run_dir: Path,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    creative = settings.get("creative", {})
    max_rounds = int(creative.get("max_image_rounds", 3))
    pass_score = int(creative.get("pass_score", 7))
    image_count = int(creative.get("image_count", 2))

    def emit(event: str, payload: dict[str, Any]) -> None:
        if on_progress:
            on_progress(event, payload)

    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    verdict_json = json.dumps(verdict, indent=2)
    rewrite_notes = ""
    promo: dict[str, Any] | None = None
    assets: list[dict[str, Any]] = []

    for attempt in range(1, max_rounds + 1):
        emit("promoter_start", {"attempt": attempt})
        promo_raw = router.complete(
            "promoter",
            roles.PROMOTER_SYSTEM,
            roles.promoter_user(claim, verdict_json, image_count, rewrite_notes),
            json_mode=True,
            temperature=0.6,
        )
        promo = parse_json(promo_raw)
        emit("promoter_done", {"attempt": attempt, "promo": promo})

        promo_context = json.dumps(
            {
                "headline": promo.get("headline"),
                "tagline": promo.get("tagline"),
                "promo_blurb": promo.get("promo_blurb"),
            },
            indent=2,
        )

        attempt_assets: list[dict[str, Any]] = []
        rewrite_parts: list[str] = []
        all_pass = True

        for idx, img_spec in enumerate(promo.get("images") or []):
            purpose = img_spec.get("purpose", "other")
            prompt = img_spec.get("prompt") or ""
            img_id = img_spec.get("id") or f"img_{idx + 1}"
            filename = f"{img_id}_a{attempt}.jpg"
            path = images_dir / filename

            emit("image_gen_start", {"attempt": attempt, "id": img_id, "prompt": prompt})
            image_client.generate(prompt, path, seed=1000 + attempt * 10 + idx)
            emit("image_gen_done", {"attempt": attempt, "id": img_id, "path": str(path)})

            emit("image_critic_start", {"attempt": attempt, "id": img_id})
            critic_raw = router.complete_vision(
                "image_critic",
                roles.IMAGE_CRITIC_SYSTEM,
                roles.image_critic_user(purpose, prompt, promo_context),
                path,
                json_mode=True,
            )
            critique = parse_json(critic_raw)
            score = float(critique.get("score", 0))
            passed = bool(critique.get("pass", False)) and score >= pass_score
            if not passed:
                all_pass = False
                note = critique.get("rewrite_notes") or "; ".join(critique.get("issues") or [])
                if note:
                    rewrite_parts.append(f"{img_id}: {note}")

            record = {
                "id": img_id,
                "attempt": attempt,
                "purpose": purpose,
                "prompt": prompt,
                "path": str(path.relative_to(run_dir)),
                "critique": critique,
                "passed": passed,
            }
            attempt_assets.append(record)
            emit("image_critic_done", {"attempt": attempt, "id": img_id, "critique": critique})

        assets.extend(attempt_assets)
        if all_pass:
            emit("creative_pass", {"attempt": attempt})
            break
        rewrite_notes = "\n".join(rewrite_parts) or "Improve clarity, composition, and brief match."
        emit("creative_retry", {"attempt": attempt, "rewrite_notes": rewrite_notes})

    assert promo is not None
    approved = [a for a in assets if a.get("passed")]
    # Prefer latest attempt images if none formally passed
    if not approved:
        last_attempt = max((a["attempt"] for a in assets), default=1)
        approved = [a for a in assets if a["attempt"] == last_attempt]

    return {
        "promo": promo,
        "assets": assets,
        "approved": approved,
        "pass_score": pass_score,
        "attempts": max((a["attempt"] for a in assets), default=0),
    }