"""Video generation via OpenRouter `/videos` API."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Iterable

import httpx

from pipeline.generate import _image_data_url


class VideoGenError(RuntimeError):
    pass


def _video_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return settings.get("video") or {}


def build_video_prompt(bible: dict[str, Any], panels: list[dict[str, Any]]) -> str:
    """Compile a short sequence description from the first N panels."""
    aesthetic = bible.get("aesthetic_name") or bible.get("aesthetic") or ""
    tone = bible.get("tone") or ""
    beats = []
    for p in panels:
        idx = p.get("index")
        beat = f"Shot {idx}: {p.get('shot_type', 'medium')} of {p.get('subject', '')} — {p.get('action', '')}"
        if p.get("emotion"):
            beat += f" (emotion: {p.get('emotion')})"
        beats.append(beat.strip())
    seq = " ".join(beats)
    return (
        f"Cinematic anime-style sequence in the aesthetic of {aesthetic}."
        f" Tone: {tone or 'storyboard animatic'}."
        f" Animate the following shots in order with gentle camera motion: {seq}"
    )


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
) -> dict[str, Any]:
    vid_cfg = _video_settings(settings)
    model = str(vid_cfg.get("model") or "google/veo-3.1-lite")
    duration = int(vid_cfg.get("duration", 4))
    resolution = str(vid_cfg.get("resolution", "720p"))
    aspect_ratio = _normalize_aspect_ratio(vid_cfg.get("aspect_ratio", "16:9"))

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
        # Use input_references to bias style toward the panels
        payload["input_references"] = [
            {"type": "image_url", "image_url": {"url": _image_data_url(Path(p))}}
            for p in list(frames)[:4]
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
        if resp.status_code >= 400 and "input_references" in payload:
            # Some video models reject reference images — retry text-only
            body = resp.text[:400]
            if "input_reference" in body or "reference" in body.lower() or resp.status_code == 400:
                payload.pop("input_references", None)
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
    # Prefer direct content URLs, then unsigned_urls if present.
    content = job.get("content") or []
    if content and isinstance(content, list):
        url = content[0].get("url")
        if url:
            return url
    unsigned = job.get("unsigned_urls") or []
    if unsigned and isinstance(unsigned, list):
        return unsigned[0]
    raise VideoGenError(f"Completed video job missing URL: {str(job)[:300]}")


def submit_first5_clip(
    settings: dict[str, Any],
    bible: dict[str, Any],
    panels: list[dict[str, Any]],
    panel_paths: list[Path],
) -> dict[str, Any]:
    """Submit a video job for the first panels. Returns the job dict (id, status, polling_url)."""
    if not panels:
        raise VideoGenError("No panels available for video generation")
    prompt = build_video_prompt(bible, panels)
    return _submit_video_job(settings, prompt, frame_paths=panel_paths)


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


def generate_first5_clip(
    settings: dict[str, Any],
    bible: dict[str, Any],
    panels: list[dict[str, Any]],
    panel_paths: list[Path],
    out_path: Path,
) -> Path:
    """Blocking variant: submit, poll to completion, download."""
    submit = submit_first5_clip(settings, bible, panels, panel_paths)
    vid_cfg = _video_settings(settings)
    max_wait = float(vid_cfg.get("max_wait_seconds", 600))
    job = _poll_video_job(submit, max_wait_s=max_wait)
    url = _extract_video_url(job)
    return download_video(url, out_path)

