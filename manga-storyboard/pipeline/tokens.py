"""Lightweight token / cost usage tracking for a run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.util import load_json, save_json


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Good enough for a usage view."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def usage_path(run_dir: Path) -> Path:
    return run_dir / "usage.json"


def load_usage(run_dir: Path) -> dict[str, Any]:
    path = usage_path(run_dir)
    if not path.exists():
        return {"calls": [], "images": 0, "videos": 0}
    try:
        data = load_json(path)
        if isinstance(data, dict):
            data.setdefault("calls", [])
            data.setdefault("images", 0)
            data.setdefault("videos", 0)
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"calls": [], "images": 0, "videos": 0}


def save_usage(run_dir: Path, usage: dict[str, Any]) -> None:
    save_json(usage_path(run_dir), usage)


def record_llm_call(
    run_dir: Path | None,
    *,
    role: str,
    model: str,
    prompt_text: str,
    response_text: str = "",
    tokens_in: int | None = None,
    tokens_out: int | None = None,
) -> None:
    if run_dir is None:
        return
    usage = load_usage(run_dir)
    tin = tokens_in if tokens_in is not None else estimate_tokens(prompt_text)
    tout = tokens_out if tokens_out is not None else estimate_tokens(response_text)
    usage["calls"].append(
        {
            "role": role,
            "model": model,
            "tokens_in": tin,
            "tokens_out": tout,
            "tokens_total": tin + tout,
        }
    )
    save_usage(run_dir, usage)


def record_image(run_dir: Path | None, count: int = 1) -> None:
    if run_dir is None:
        return
    usage = load_usage(run_dir)
    usage["images"] = int(usage.get("images", 0) or 0) + count
    save_usage(run_dir, usage)


def record_video(run_dir: Path | None, count: int = 1) -> None:
    if run_dir is None:
        return
    usage = load_usage(run_dir)
    usage["videos"] = int(usage.get("videos", 0) or 0) + count
    save_usage(run_dir, usage)


def summarize_usage(usage: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    costs = (settings or {}).get("costs") or {}
    per_1k = float(costs.get("per_1k_tokens_usd", 0.002) or 0.002)
    per_image = float(costs.get("per_image_usd", 0.03) or 0.03)
    per_video = float(costs.get("per_video_usd", 0.20) or 0.20)

    calls = usage.get("calls") or []
    tokens = sum(int(c.get("tokens_total", 0) or 0) for c in calls)
    by_role: dict[str, int] = {}
    for c in calls:
        role = c.get("role") or "other"
        by_role[role] = by_role.get(role, 0) + int(c.get("tokens_total", 0) or 0)

    images = int(usage.get("images", 0) or 0)
    videos = int(usage.get("videos", 0) or 0)
    llm_cost = (tokens / 1000.0) * per_1k
    image_cost = images * per_image
    video_cost = videos * per_video
    return {
        "tokens": tokens,
        "by_role": by_role,
        "images": images,
        "videos": videos,
        "est_cost_usd": round(llm_cost + image_cost + video_cost, 4),
        "breakdown_usd": {
            "llm": round(llm_cost, 4),
            "images": round(image_cost, 4),
            "videos": round(video_cost, 4),
        },
    }
