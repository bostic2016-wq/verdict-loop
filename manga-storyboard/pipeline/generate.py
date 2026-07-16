"""Image generation backends."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


class ImageGenError(RuntimeError):
    pass


def generate_panel_image(
    settings: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    out_path: Path,
    *,
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
) -> Path:
    backend = _resolve_backend(settings)
    width = width or settings.get("defaults", {}).get("image_width", 768)
    height = height or settings.get("defaults", {}).get("image_height", 1024)

    # Fold negatives into the positive prompt for providers that ignore negative_prompt
    full_prompt = prompt.strip()
    if negative_prompt and backend in {"openrouter", "pollinations"}:
        full_prompt = f"{full_prompt}. Avoid: {negative_prompt[:400]}"

    if backend == "mock":
        return _mock_image(out_path, full_prompt, width, height)
    if backend == "fal_illustrious":
        return _fal_generate(prompt, negative_prompt, out_path, width, height, seed)
    if backend == "openrouter":
        try:
            return _openrouter_images_api(settings, full_prompt, out_path, seed=seed)
        except Exception:
            # Free fallback so cloud runs still get real pictures
            return _pollinations(full_prompt, out_path, width, height, seed)
    if backend == "openrouter_gpt_image":
        return _openrouter_chat_image(settings, full_prompt, out_path)
    if backend == "pollinations":
        return _pollinations(full_prompt, out_path, width, height, seed)
    raise ImageGenError(f"Unknown image_backend: {backend}")


def _resolve_backend(settings: dict[str, Any]) -> str:
    if os.getenv("MANGA_MOCK_IMAGES") == "1":
        return "mock"
    configured = (settings.get("models") or {}).get("image_backend") or "openrouter"
    if configured == "auto":
        if os.getenv("OPENROUTER_API_KEY"):
            return "openrouter"
        if os.getenv("FAL_KEY"):
            return "fal_illustrious"
        return "pollinations"
    # Never silently stay on mock in cloud when a real key exists
    if configured == "mock" and os.getenv("OPENROUTER_API_KEY") and os.getenv("MANGA_FORCE_MOCK") != "1":
        return "openrouter"
    return configured


def _mock_image(out_path: Path, prompt: str, width: int, height: int) -> Path:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (24, 24, 28))
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, width - 16, height - 16], outline=(200, 200, 200), width=3)
    text = (prompt[:180] + "…") if len(prompt) > 180 else prompt
    y = 40
    for line in _wrap(text, 42):
        draw.text((32, y), line, fill=(230, 230, 230))
        y += 22
        if y > height - 40:
            break
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = " ".join(cur + [w])
        if len(trial) <= width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines or [""]


def _fal_generate(
    prompt: str,
    negative_prompt: str,
    out_path: Path,
    width: int,
    height: int,
    seed: int | None,
) -> Path:
    key = os.getenv("FAL_KEY")
    if not key:
        raise ImageGenError("FAL_KEY missing — set it or use image_backend: openrouter")

    model = os.getenv("FAL_IMAGE_MODEL") or "fal-ai/flux/dev"
    payload: dict[str, Any] = {
        "prompt": prompt,
        "image_size": {"width": width, "height": height},
        "num_images": 1,
        "enable_safety_checker": True,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    if seed is not None:
        payload["seed"] = seed

    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=180.0) as client:
        url = f"https://fal.run/{model}"
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise ImageGenError(f"Fal error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        image_url = None
        if isinstance(data.get("images"), list) and data["images"]:
            image_url = data["images"][0].get("url")
        elif data.get("image"):
            image_url = data["image"].get("url") if isinstance(data["image"], dict) else data["image"]
        if not image_url:
            raise ImageGenError(f"Fal response missing image URL: {str(data)[:400]}")
        img_resp = client.get(image_url)
        img_resp.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(img_resp.content)
    return out_path


def _openrouter_images_api(
    settings: dict[str, Any],
    prompt: str,
    out_path: Path,
    *,
    seed: int | None = None,
) -> Path:
    """Same OpenRouter /images endpoint Verdict Loop uses (FLUX)."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ImageGenError("OPENROUTER_API_KEY missing")
    model = (settings.get("models") or {}).get("image_model") or "black-forest-labs/flux.2-pro"
    url = (settings.get("openrouter") or {}).get("image_url") or "https://openrouter.ai/api/v1/images"
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt.strip(),
        "aspect_ratio": "3:4",
        "output_format": "jpeg",
    }
    if seed is not None:
        payload["seed"] = seed
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/bostic2016-wq/verdict-loop",
        "X-Title": "Manga Storyboard",
    }
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise ImageGenError(f"OpenRouter images error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
    images = data.get("data") or []
    if not images or not images[0].get("b64_json"):
        raise ImageGenError(f"OpenRouter image response missing data: {str(data)[:400]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(images[0]["b64_json"]))
    return out_path


def _openrouter_chat_image(
    settings: dict[str, Any],
    prompt: str,
    out_path: Path,
) -> Path:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ImageGenError("OPENROUTER_API_KEY missing")
    model = (settings.get("models") or {}).get("image_model", "openai/gpt-image-1")
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise ImageGenError(f"OpenRouter image error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        message = (data.get("choices") or [{}])[0].get("message") or {}
        images = message.get("images") or []
        if images:
            url_or_b64 = images[0].get("image_url", {}).get("url") or images[0].get("url")
            if url_or_b64 and url_or_b64.startswith("data:"):
                b64 = url_or_b64.split(",", 1)[1]
                out_path.write_bytes(base64.b64decode(b64))
                return out_path
            if url_or_b64 and url_or_b64.startswith("http"):
                img = client.get(url_or_b64)
                img.raise_for_status()
                out_path.write_bytes(img.content)
                return out_path
    raise ImageGenError("Could not parse OpenRouter chat image response")


def _pollinations(
    prompt: str,
    out_path: Path,
    width: int,
    height: int,
    seed: int | None,
) -> Path:
    encoded = quote(prompt.strip()[:1200], safe="")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&model=flux&nologo=true&private=true"
    )
    if seed is not None:
        url += f"&seed={seed}"
    headers = {}
    key = os.getenv("POLLINATIONS_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise ImageGenError(f"Pollinations error {resp.status_code}: {resp.text[:300]}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
    return out_path
