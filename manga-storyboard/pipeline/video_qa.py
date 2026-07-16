"""QA for generated video clips — metadata checks + vision critic on sampled frames."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.creative_bible import bible_excerpt
from pipeline.roles import VIDEO_VISION_SYSTEM, VIDEO_VISION_USER
from pipeline.router import DirectorRouter
from pipeline.util import parse_json, save_json


VIDEO_WEIGHTS = {
    "panel_match": 0.30,
    "character_consistency": 0.20,
    "outfit_consistency": 0.15,
    "style_match": 0.10,
    "motion_relevance": 0.10,
    "technical_quality": 0.15,
}


def extract_frames(video_path: Path, out_dir: Path, count: int = 4) -> list[Path]:
    """Sample evenly spaced frames from an MP4 using OpenCV."""
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("opencv-python-headless is required for video QA") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 24.0
    duration = (total / fps) if total > 0 else 0.0

    if total <= 0:
        # Fallback: grab a few sequential frames
        frames: list[Path] = []
        for i in range(count):
            ok, frame = cap.read()
            if not ok:
                break
            dest = out_dir / f"frame_{i:02d}.jpg"
            cv2.imwrite(str(dest), frame)
            frames.append(dest)
        cap.release()
        return frames

    indexes = [int(i * (total - 1) / max(count - 1, 1)) for i in range(count)]
    frames = []
    for i, fi in enumerate(indexes):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ok, frame = cap.read()
        if not ok:
            continue
        dest = out_dir / f"frame_{i:02d}.jpg"
        cv2.imwrite(str(dest), frame)
        frames.append(dest)
    cap.release()
    return frames


def metadata_qa(video_path: Path, *, expected_duration: float | None = None) -> dict[str, Any]:
    issues: list[str] = []
    if not video_path.exists():
        return {"pass": False, "issues": ["video file missing"], "duration": 0, "bytes": 0}
    size = video_path.stat().st_size
    if size < 20_000:
        issues.append(f"video file too small ({size} bytes) — likely corrupt or empty")

    duration = 0.0
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 24.0
            duration = total / fps if total else 0.0
            cap.release()
        else:
            issues.append("cannot open video for metadata check")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"metadata check failed: {exc}")

    if expected_duration and duration > 0:
        # Allow generous slack — providers don't always hit exact seconds
        if abs(duration - expected_duration) > max(3.0, expected_duration * 0.75):
            issues.append(f"duration ~{duration:.1f}s differs from requested {expected_duration}s")

    return {
        "pass": not issues,
        "issues": issues,
        "duration": round(duration, 2),
        "bytes": size,
    }


def critique_video(
    router: DirectorRouter,
    bible: dict[str, Any],
    panels: list[dict[str, Any]],
    video_path: Path,
    source_panel_paths: list[Path],
    *,
    direction: str = "",
    pass_score: float = 0.65,
    expected_duration: float | None = None,
) -> dict[str, Any]:
    meta = metadata_qa(video_path, expected_duration=expected_duration)
    if not meta["pass"] and meta.get("bytes", 0) < 20_000:
        return {
            "pass": False,
            "score": 0.0,
            "issues": meta["issues"],
            "rewrite_notes": "regenerate clip; previous output was empty or corrupt",
            "metadata": meta,
            "dimensions": {},
        }

    frame_dir = video_path.parent / f"{video_path.stem}_frames"
    try:
        frames = extract_frames(video_path, frame_dir, count=4)
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "score": 0.2,
            "issues": meta["issues"] + [f"frame extraction failed: {exc}"],
            "rewrite_notes": "regenerate clip with clearer single-panel reference",
            "metadata": meta,
            "dimensions": {},
        }

    if not frames:
        return {
            "pass": False,
            "score": 0.1,
            "issues": meta["issues"] + ["no frames extracted"],
            "rewrite_notes": "regenerate clip",
            "metadata": meta,
            "dimensions": {},
        }

    panel_summary = "\n".join(
        f"P{p.get('index')}: {p.get('shot_type')} | {p.get('subject')} | {p.get('action')}" for p in panels
    )
    user = VIDEO_VISION_USER.format(
        bible_excerpt=bible_excerpt(bible),
        panels=panel_summary,
        direction=direction or "(none)",
        pass_score=pass_score,
    )
    # IMAGE order: source panels first, then sampled video frames
    images = [p for p in source_panel_paths if p.exists()][:3] + frames[:4]
    user += (
        "\n\nImage order: first image(s) are the SOURCE PANEL(s). "
        "Later images are FRAMES sampled from the generated video. "
        "Judge whether the video frames match the source panel(s)."
    )

    try:
        raw = router.complete_vision("vision_critic", VIDEO_VISION_SYSTEM, user, images, json_mode=True)
        critique = parse_json(raw)
    except Exception as exc:  # noqa: BLE001 — soft fail so user can still preview
        return {
            "pass": True,
            "score": pass_score,
            "issues": meta["issues"] + [f"vision critic unavailable: {exc}"],
            "rewrite_notes": "",
            "soft_pass": True,
            "metadata": meta,
            "dimensions": {},
            "frames": [str(f) for f in frames],
        }

    dims = critique.get("dimensions") or {}
    if dims:
        score = sum(float(dims.get(k, 0) or 0) * w for k, w in VIDEO_WEIGHTS.items())
        critique["score"] = round(score, 3)
        hard_fail = (
            float(dims.get("panel_match", 1) or 1) < 0.45
            or float(dims.get("technical_quality", 1) or 1) < 0.4
            or float(dims.get("character_consistency", 1) or 1) < 0.4
        )
        critique["pass"] = bool(critique.get("pass")) and score >= pass_score and not hard_fail
    else:
        critique["pass"] = bool(critique.get("pass")) and float(critique.get("score", 0) or 0) >= pass_score

    issues = list(critique.get("issues") or []) + list(meta.get("issues") or [])
    critique["issues"] = issues
    critique.setdefault("rewrite_notes", "")
    if not critique.get("pass") and not critique.get("rewrite_notes"):
        critique["rewrite_notes"] = (
            "Hold the source panel composition exactly; animate only subtle motion; "
            "no new scene, no blur, keep outfits and faces from the source panel."
        )
    critique["metadata"] = meta
    critique["frames"] = [str(f) for f in frames]
    critique["dimensions"] = dims
    return critique


def save_qa(run_dir: Path, output_id: str, critique: dict[str, Any]) -> Path:
    dest = run_dir / "video" / f"output_{output_id}_qa.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    save_json(dest, critique)
    return dest
