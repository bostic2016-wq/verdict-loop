"""Environment-driven configuration.

All credentials come from environment variables (or .env / Streamlit secrets)
and are never hardcoded. Model ids may be overridden per-run via env:

  OPENROUTER_API_KEY   required for generation + vision QA (unless mock)
  SEEDREAM_MODEL       image model id (default bytedance-seed/seedream-4.5)
  VISION_MODEL         vision QA model id (litellm id, e.g. openrouter/google/gemini-2.5-flash)
  MANGA_MOCK_IMAGES=1  placeholder images, no API spend
"""

from __future__ import annotations

import os
from typing import Any

from pipeline.util import load_settings

DEFAULT_SEEDREAM_MODEL = "bytedance-seed/seedream-4.5"


class ConfigError(RuntimeError):
    pass


def is_mock() -> bool:
    return os.getenv("MANGA_MOCK_IMAGES") == "1"


def require_openrouter_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ConfigError(
            "OPENROUTER_API_KEY is not set. Export it or add it to manga-storyboard/.env "
            "(never hardcode it). Use MANGA_MOCK_IMAGES=1 to run without API spend."
        )
    return key


def seedream_model() -> str:
    return os.getenv("SEEDREAM_MODEL", "").strip() or DEFAULT_SEEDREAM_MODEL


def load_config(*, profile: str | None = None, strict: bool = False) -> dict[str, Any]:
    """Load config.yaml + .env and apply env/CLI overrides.

    profile: image profile id (e.g. 'anime_seedream'); Seedream model from
             SEEDREAM_MODEL is prepended to the profile chain.
    strict:  disable silent image-backend fallbacks (loop/CLI mode).
    """
    settings = load_settings()
    models = settings.setdefault("models", {})

    if profile:
        models["image_profile"] = profile

    # Env-selected Seedream model leads the active chain.
    seedream = seedream_model()
    profiles = models.setdefault("image_profiles", {})
    anime = profiles.setdefault("anime_seedream", {"chain": [seedream]})
    chain = [m for m in (anime.get("chain") or []) if m != seedream]
    anime["chain"] = [seedream, *chain]

    vision = os.getenv("VISION_MODEL", "").strip()
    if vision:
        models["vision_critic"] = vision
        settings.setdefault("fallback_models", {})["vision_critic"] = vision

    if strict:
        settings.setdefault("generation", {})["strict"] = True

    if not is_mock():
        require_openrouter_key()
    return settings
