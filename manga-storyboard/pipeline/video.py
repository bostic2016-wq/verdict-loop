"""Video generation via OpenRouter `/videos` API — selected-panel shot builder."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

import httpx

from pipeline.generate import _image_data_url
from pipeline.util import save_json


class VideoGenError(RuntimeError):
    pass


def _video_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return settings.get("video") or {}


def build_shot_prompt(
    bible: dict[str, Any],
    panels: list[dict[str, Any]],
    *,
    direction: str = "",
    motion_style: str = "subtle",
) -> str:
    """Compile a strict shot-spec prompt for selected panel(s)."""
    aesthetic = bible.get("aesthetic_name") or bible.get("aesthetic") or ""
    tone = bible.get("tone") or ""
    chars = bible.get("characters") or []
    char_lock = "; ".join(
        f"{c.get('name')}: {c.get('look') or 'keep design from reference'}" for c in chars if c.get("name")
    )

    indexes = [str(p.get("index")) for p in panels]
    single = len(panels) == 1

    beats = []
    for p in panels:
        idx = p.get("index")
        cast = ", ".join(p.get("characters") or []) or "as shown"
        beat = (
            f"KEYFRAME Panel {idx}: shot={p.get('shot_type', 'medium')}; "
            f"subject={p.get('subject', '')}; action={p.get('action', '')}; "
            f"emotion={p.get('emotion', '')}; setting={p.get('setting', '')}; "
            f"characters={cast}"
        )
        beats.append(beat)

    motion_map = {
        "subtle": "subtle natural micro-motion only (hair, cloth, eyes, breathing)",
        "action": "dynamic action motion matching the panel beat",
        "camera pan": "slow camera pan while holding composition",
        "zoom-in": "gentle camera push-in / zoom toward the subject",
        "hold frame": "near-static hold with tiny life motion only",
    }
    motion = motion_map.get(motion_style, motion_map["subtle"])

    if single:
        core = (
            f"Animate ONE manga panel as a short clip. "
            f"Hold the original Panel {indexes[0]} composition exactly. "
            f"Only animate: {motion}. "
            f"Do NOT invent a new scene. Do NOT redesign characters. "
            f"No scene change, no costume change, no extra people."
        )
    else:
        core = (
            f"Animate a short sequence using these panels IN ORDER as keyframes: {', '.join(indexes)}. "
            f"Move through each panel beat without skipping indexes. "
            f"Use each selected panel image as a visual keyframe/reference. "
            f"Motion style: {motion}. "
            f"Do NOT invent new scenes or drop characters."
        )

    parts = [
        f"Cinematic anime-style clip matching aesthetic: {aesthetic}.",
        f"Tone: {tone or 'storyboard animatic'}.",
        core,
        "Use the attached source panel image(s) as the visual reference — match faces, outfits, colors, and framing.",
        f"Character lock: {char_lock or 'keep all characters on-model from references'}.",
        "Forbidden: wrong panel, wrong character, blurry mush, washed colors, random aura/energy unless the beat requires it,",
        "speech bubbles, text overlays, watermarks.",
        " ".join(beats),
    ]
    if direction.strip():
        parts.append(f"Director note: {direction.strip()}")
    return " ".join(p for p in parts if p)


# Back-compat alias used by older callers
def build_video_prompt(bible: dict[str, Any], panels: list[dict[str, Any]]) -> str:
    return build_shot_prompt(bible, panels)


def _normalize_aspect_ratio(value: Any) -> str:
    """Guard against YAML parsing 16:9 as the base-60 integer 969."""
    text = str(value or "").strip()
    if ":" in text:
        return text
    known = {"969": "16:9", "549": "9:16", "243": "4:3", "184": "3:4"}
    return known.get(text, "16:9")


def _submit_video_job(
    settings: dict[str, Any],
    prompt: str,
    frame_paths: Iterable[Path] | None = None,
    *,
    duration: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
) -> dict[str, Any]:
    vid_cfg = _video_settings(settings)
    model = str(vid_cfg.get("model") or "google/veo-3.1-lite")
    duration = int(duration if duration is not None else vid_cfg.get("duration", 4))
    resolution = str(resolution or vid_cfg.get("resolution", "720p"))
    aspect_ratio = _normalize_aspect_ratio(aspect_ratio or vid_cfg.get("aspect_ratio", "16:9"))

    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise VideoGenError("OPENROUTER_API_KEY missing for video generation")

    url = (settings.get("openrouter") or {}).get("video_url") or "https://openrouter.ai/api/v1/videos"

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt.strip(),
        "duration": duration,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "generate_audio": False,
    }

    frames = [p for p in (frame_paths or []) if p and Path(p).exists()]
    if frames:
        # Prefer first frame as primary for single-panel fidelity
        payload["input_references"] = [
            {"type": "image_url", "image_url": {"url": _image_data_url(Path(p))}}
            for p in list(frames)[:4]
        ]
        # Also try frame_images for image-to-video models that support it
        payload["frame_images"] = [
            {"type": "image_url", "image_url": {"url": _image_data_url(Path(frames[0]))}}
        ]

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/bostic2016-wq/verdict-loop",
        "X-Title": "Manga Storyboard Video",
    }
    timeout = httpx.Timeout(60.0, connect=10.0)
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400 and ("frame_images" in payload or "input_references" in payload):
            body = resp.text[:500].lower()
            # Strip unsupported fields and retry once
            if "frame_image" in body or "frame_images" in body:
                payload.pop("frame_images", None)
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400 and ("input_reference" in body or "reference" in body):
                payload.pop("input_references", None)
                payload.pop("frame_images", None)
                resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise VideoGenError(f"OpenRouter video error {resp.status_code}: {resp.text[:400]}")
        return resp.json()


def _poll_video_job(job: dict[str, Any], max_wait_s: float = 240.0) -> dict[str, Any]:
    polling_url = job.get("polling_url")
    if not polling_url:
        raise VideoGenError(f"Video job missing polling_url: {job}")

    key = os.getenv("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    start = time.time()
    timeout = httpx.Timeout(30.0, connect=10.0)
    last = job

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        while True:
            if time.time() - start > max_wait_s:
                raise VideoGenError(f"Video job timed out after {max_wait_s:.0f}s (last status={last.get('status')})")
            resp = client.get(polling_url, headers=headers)
            if resp.status_code >= 400:
                raise VideoGenError(f"Polling error {resp.status_code}: {resp.text[:300]}")
            last = resp.json()
            status = (last.get("status") or "").lower()
            if status in {"completed", "failed", "cancelled", "expired"}:
                break
            time.sleep(3.0)

    if last.get("status") != "completed":
        raise VideoGenError(f"Video job did not complete successfully: {last.get('status')}")
    return last


def _extract_video_url(job: dict[str, Any]) -> str:
    content = job.get("content") or []
    if content and isinstance(content, list):
        url = content[0].get("url")
        if url:
            return url
    unsigned = job.get("unsigned_urls") or []
    if unsigned and isinstance(unsigned, list):
        return unsigned[0]
    raise VideoGenError(f"Completed video job missing URL: {str(job)[:300]}")


def submit_selected_clip(
    settings: dict[str, Any],
    bible: dict[str, Any],
    panels: list[dict[str, Any]],
    panel_paths: list[Path],
    *,
    direction: str = "",
    motion_style: str = "subtle",
    duration: int | None = None,
    aspect_ratio: str | None = None,
) -> dict[str, Any]:
    """Submit a video job for user-selected panels. Returns job + prompt metadata."""
    if not panels:
        raise VideoGenError("Select at least one panel to animate")
    prompt = build_shot_prompt(bible, panels, direction=direction, motion_style=motion_style)
    job = _submit_video_job(
        settings,
        prompt,
        frame_paths=panel_paths,
        duration=duration,
        aspect_ratio=aspect_ratio,
    )
    return {
        "job": job,
        "prompt": prompt,
        "panel_indexes": [p.get("index") for p in panels],
        "direction": direction,
        "motion_style": motion_style,
        "model": (_video_settings(settings).get("model") or "google/veo-3.1-lite"),
        "output_id": uuid.uuid4().hex[:10],
    }


# Back-compat wrappers
def submit_first5_clip(
    settings: dict[str, Any],
    bible: dict[str, Any],
    panels: list[dict[str, Any]],
    panel_paths: list[Path],
) -> dict[str, Any]:
    result = submit_selected_clip(settings, bible, panels, panel_paths)
    return result["job"]


def check_video_job(job: dict[str, Any]) -> dict[str, Any]:
    """Single non-blocking status check. Returns {'status': ..., 'url': ...?}."""
    polling_url = job.get("polling_url")
    if not polling_url:
        raise VideoGenError(f"Video job missing polling_url: {str(job)[:200]}")
    key = os.getenv("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
        resp = client.get(polling_url, headers=headers)
        if resp.status_code >= 400:
            raise VideoGenError(f"Polling error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
    status = (data.get("status") or "").lower()
    result: dict[str, Any] = {"status": status}
    if status == "completed":
        result["url"] = _extract_video_url(data)
    elif status in {"failed", "cancelled", "expired"}:
        result["error"] = data.get("error") or f"job {status}"
    return result


def download_video(url: str, out_path: Path) -> Path:
    key = os.getenv("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key and "openrouter.ai" in url else {}
    timeout = httpx.Timeout(180.0, connect=10.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise VideoGenError(f"Downloading video failed {resp.status_code}: {resp.text[:300]}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
    return out_path


def save_output_record(run_dir: Path, record: dict[str, Any]) -> Path:
    out_id = record.get("output_id") or uuid.uuid4().hex[:10]
    dest = run_dir / "outputs" / f"output_{out_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    save_json(dest, record)
    return dest


def generate_first5_clip(
    settings: dict[str, Any],
    bible: dict[str, Any],
    panels: list[dict[str, Any]],
    panel_paths: list[Path],
    out_path: Path,
) -> Path:
    """Blocking variant: submit, poll to completion, download."""
    meta = submit_selected_clip(settings, bible, panels, panel_paths)
    vid_cfg = _video_settings(settings)
    max_wait = float(vid_cfg.get("max_wait_seconds", 600))
    job = _poll_video_job(meta["job"], max_wait_s=max_wait)
    url = _extract_video_url(job)
    return download_video(url, out_path)
