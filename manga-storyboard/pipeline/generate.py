"""Image generation backends — OpenRouter Nano Banana Pro / FLUX with character references."""

from __future__ import annotations

import base64
import io
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


IMAGE_PIPELINE_BUILD = "2026-07-16-multi-model"

# Nano Banana Pro first (best multi-reference character fidelity).
# FLUX is the reliable fallback. GPT Image is omitted — openai/gpt-image-2
# hung past 45s in production probes and made panel 5 look "stuck".
DEFAULT_MODEL_CHAIN = [
    "google/gemini-3-pro-image",
    "black-forest-labs/flux.2-pro",
]

# Per-model read timeout. Keep this short so a bad model cannot freeze a batch.
MODEL_TIMEOUT_S = 75.0
CONNECT_TIMEOUT_S = 10.0
REF_MAX_SIDE = 768
REF_JPEG_QUALITY = 80


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
    reference_paths: list[Path] | None = None,
    strict: bool | None = None,
) -> Path:
    """Generate one panel image.

    When models.image_run_mode is all_selected, every checked OpenRouter model
    gets its own variant (prompt shaped per model, Desktop folder per model).
    The first success becomes the primary path used by the filmstrip/QA.
    """
    if strict is None:
        strict = bool((settings.get("generation") or {}).get("strict"))
    backend = _resolve_backend(settings)
    width = width or settings.get("defaults", {}).get("image_width", 768)
    height = height or settings.get("defaults", {}).get("image_height", 1024)

    from pipeline.desktop_export import save_image_to_desktop
    from pipeline.image_catalog import model_slug, run_mode, selected_model_ids
    from pipeline.model_prompts import adapt_prompt_for_model, adapt_prompt_for_settings

    panel_index = _panel_index_from_path(out_path)

    def _finalize(path: Path, *, model_id: str | None = None, used_backend: str | None = None) -> Path:
        try:
            desktop = save_image_to_desktop(
                path,
                model_id=model_id,
                backend=used_backend or backend,
                panel_index=panel_index,
                settings=settings,
            )
            if desktop:
                print(f"[manga-gen] desktop copy → {desktop}", file=sys.stderr, flush=True)
        except Exception as exc:  # noqa: BLE001 — desktop export must never break generation
            print(f"[manga-gen] desktop export skipped: {exc}", file=sys.stderr, flush=True)
        return path

    def _write_one(model: str | None, dest: Path, *, used_backend: str) -> Path:
        if used_backend == "mock":
            adapted_p, adapted_n = adapt_prompt_for_settings(prompt, negative_prompt or "", settings)
            if model:
                adapted_p, adapted_n = adapt_prompt_for_model(prompt, negative_prompt or "", model)
            full = _with_avoid(adapted_p, adapted_n)
            return _finalize(_mock_image(dest, full, width, height), model_id=model, used_backend="mock")
        if used_backend == "pollinations":
            adapted_p, adapted_n = adapt_prompt_for_settings(prompt, negative_prompt or "", settings)
            full = _with_avoid(adapted_p, adapted_n)
            return _finalize(
                _pollinations(full, dest, width, height, seed),
                used_backend="pollinations",
            )
        assert model is not None
        model_prompt, model_neg = adapt_prompt_for_model(prompt, negative_prompt or "", model)
        full_prompt = _with_avoid(model_prompt, model_neg)
        print(f"[manga-gen] trying {model} → {dest.name}", file=sys.stderr, flush=True)
        path = _openrouter_images_api(
            settings,
            model,
            full_prompt,
            dest,
            seed=seed,
            reference_paths=reference_paths,
        )
        print(f"[manga-gen] ok {model} → {dest.name}", file=sys.stderr, flush=True)
        return _finalize(path, model_id=model, used_backend="openrouter")

    # ---- Multi-model: run every selected model, keep all variants ----
    if run_mode(settings) == "all_selected":
        models = selected_model_ids(settings)
        if not models:
            models = _model_chain(settings)[:1]
        variants: list[dict[str, Any]] = []
        primary: Path | None = None
        last_err: Exception | None = None
        used = "mock" if backend == "mock" else ("pollinations" if backend == "pollinations" else "openrouter")
        for model in models:
            slug = model_slug(model)
            dest = out_path.with_name(f"{out_path.stem}__{slug}{out_path.suffix}")
            try:
                if used == "openrouter":
                    path = _write_one(model, dest, used_backend="openrouter")
                else:
                    path = _write_one(model, dest, used_backend=used)
                variants.append({"model": model, "path": str(path), "ok": True})
                if primary is None:
                    primary = path
            except Exception as exc:  # noqa: BLE001 — keep going so other models still run
                last_err = exc
                print(f"[manga-gen] fail {model}: {exc}", file=sys.stderr, flush=True)
                variants.append({"model": model, "path": None, "ok": False, "error": str(exc)})
        if primary is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(primary.read_bytes())
            _write_variants_sidecar(
                out_path,
                variants,
                primary_model=next((v["model"] for v in variants if v.get("ok")), None),
            )
            return out_path
        if used == "openrouter" and strict:
            raise ImageGenError(f"All selected image models failed: {last_err}")
        # else fall through to single-path behavior

    # ---- Single / fallback chain (original behavior) ----
    if backend == "mock":
        return _write_one(None, out_path, used_backend="mock")
    if backend == "pollinations":
        if strict:
            raise ImageGenError(
                "OPENROUTER_API_KEY missing — strict mode does not fall back to Pollinations"
            )
        return _write_one(None, out_path, used_backend="pollinations")

    last_err = None
    for model in _model_chain(settings):
        try:
            path = _write_one(model, out_path, used_backend="openrouter")
            _write_variants_sidecar(
                out_path,
                [{"model": model, "path": str(path), "ok": True}],
                primary_model=model,
            )
            return path
        except Exception as exc:  # noqa: BLE001 — try next model
            last_err = exc
            print(f"[manga-gen] fail {model}: {exc}", file=sys.stderr, flush=True)
    if strict:
        raise ImageGenError(f"All OpenRouter image models failed: {last_err}")
    try:
        print("[manga-gen] falling back to pollinations", file=sys.stderr, flush=True)
        return _write_one(None, out_path, used_backend="pollinations")
    except Exception as exc:  # noqa: BLE001
        raise ImageGenError(f"All image backends failed: {last_err}; pollinations: {exc}") from exc


def _write_variants_sidecar(
    out_path: Path,
    variants: list[dict[str, Any]],
    *,
    primary_model: str | None,
) -> None:
    import json

    side = out_path.with_name(out_path.stem + ".variants.json")
    side.write_text(
        json.dumps(
            {"primary_model": primary_model, "variants": variants},
            indent=2,
        ),
        encoding="utf-8",
    )


def load_variants_sidecar(out_path: Path) -> list[dict[str, Any]]:
    import json

    side = out_path.with_name(out_path.stem + ".variants.json")
    if not side.exists():
        # Also check attempt path stem without _aN for multi writes that used out_path stem
        return []
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
        return list(data.get("variants") or [])
    except Exception:  # noqa: BLE001
        return []


def _with_avoid(prompt: str, negative_prompt: str) -> str:
    full = prompt.strip()
    if negative_prompt:
        full = f"{full}. Avoid: {negative_prompt[:400]}"
    return full


def _panel_index_from_path(out_path: Path) -> int | None:
    """Best-effort panel index from names like panel_003.png / panel_003_a0.png."""
    stem = out_path.stem
    parts = stem.split("_")
    for part in parts:
        if part.isdigit():
            return int(part)
        if part.startswith("a") and part[1:].isdigit():
            continue
    return None


def _model_chain(settings: dict[str, Any]) -> list[str]:
    models_cfg = settings.get("models") or {}
    # Prefer explicit image profiles (v5)
    profile = models_cfg.get("image_profile")
    profiles = models_cfg.get("image_profiles") or {}
    if profile and isinstance(profiles, dict):
        prof = profiles.get(profile) or {}
        chain = prof.get("chain")
        if isinstance(chain, list) and chain:
            # Drop known-hanging GPT Image 2 unless the chain is just that one model
            return [str(m) for m in chain if str(m) != "openai/gpt-image-2" or len(chain) == 1]

    # Backwards-compatible: global image_model_chain
    chain = models_cfg.get("image_model_chain")
    if isinstance(chain, list) and chain:
        return [str(m) for m in chain if str(m) != "openai/gpt-image-2" or len(chain) == 1]
    primary = models_cfg.get("image_model")
    out = [primary] if primary else []
    for m in DEFAULT_MODEL_CHAIN:
        if m not in out:
            out.append(m)
    return out


def _resolve_backend(settings: dict[str, Any]) -> str:
    if os.getenv("MANGA_MOCK_IMAGES") == "1":
        return "mock"
    configured = (settings.get("models") or {}).get("image_backend") or "openrouter"
    if configured == "mock" and os.getenv("OPENROUTER_API_KEY") and os.getenv("MANGA_FORCE_MOCK") != "1":
        return "openrouter"
    if configured in {"openrouter", "auto", "openrouter_flux", "flux", "fal_illustrious", "openrouter_gpt_image"}:
        return "openrouter" if os.getenv("OPENROUTER_API_KEY") else "pollinations"
    return configured


def _image_data_url(path: Path) -> str:
    """Encode a reference image as a compressed JPEG data URL (avoids huge payloads)."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            scale = min(1.0, REF_MAX_SIDE / max(w, h))
            if scale < 1.0:
                img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=REF_JPEG_QUALITY, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
    except Exception:  # noqa: BLE001 — fall back to raw bytes
        suffix = path.suffix.lower()
        mime = {
            ".png": "image/png",
            ".webp": "image/webp",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(suffix, "image/jpeg")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"


def _openrouter_images_api(
    settings: dict[str, Any],
    model: str,
    prompt: str,
    out_path: Path,
    *,
    seed: int | None = None,
    reference_paths: list[Path] | None = None,
) -> Path:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ImageGenError("OPENROUTER_API_KEY missing")
    url = (settings.get("openrouter") or {}).get("image_url") or "https://openrouter.ai/api/v1/images"

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt.strip(),
        "aspect_ratio": "3:4",
        "output_format": "jpeg",
    }
    refs = [p for p in (reference_paths or []) if p and Path(p).exists()]
    if refs:
        payload["input_references"] = [
            {"type": "image_url", "image_url": {"url": _image_data_url(Path(p))}}
            for p in refs[:4]
        ]
    if seed is not None:
        payload["seed"] = seed

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/bostic2016-wq/verdict-loop",
        "X-Title": "Manga Storyboard",
    }
    t0 = time.time()
    timeout = httpx.Timeout(MODEL_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise ImageGenError(f"OpenRouter {model} error {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
    print(f"[manga-gen] {model} responded in {time.time() - t0:.1f}s", file=sys.stderr, flush=True)

    images = data.get("data") or []
    if images and images[0].get("b64_json"):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(images[0]["b64_json"]))
        return out_path
    if images and images[0].get("url"):
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=CONNECT_TIMEOUT_S)) as client:
            img = client.get(images[0]["url"])
            img.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(img.content)
        return out_path
    raise ImageGenError(f"OpenRouter {model} response missing image data: {str(data)[:300]}")


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
    with httpx.Client(timeout=httpx.Timeout(90.0, connect=CONNECT_TIMEOUT_S), follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise ImageGenError(f"Pollinations error {resp.status_code}: {resp.text[:300]}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
    return out_path
