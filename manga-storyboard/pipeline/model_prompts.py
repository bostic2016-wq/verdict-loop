"""Model-aware prompt adaptation.

When the user picks Nano Banana, Seedream, FLUX, etc., we reshape the same
storyboard brief into a prompt that plays to that model's strengths.
"""

from __future__ import annotations

from typing import Any

# Profile id → primary model family used for compile-time adaptation
PROFILE_FAMILY = {
    "nano_banana_flux": "nano_banana",
    "anime_seedream": "seedream",
}

# OpenRouter model id substring → family
MODEL_FAMILY_HINTS = (
    ("seedream", "seedream"),
    ("bytedance-seed", "seedream"),
    ("gemini", "nano_banana"),
    ("nano-banana", "nano_banana"),
    ("imagen", "nano_banana"),
    ("flux", "flux"),
    ("black-forest", "flux"),
)


FAMILY_HINTS: dict[str, dict[str, str]] = {
    "nano_banana": {
        "prefix": (
            "Photoreal character-reference fidelity, multi-subject coherence. "
            "Match attached reference faces and outfits exactly. "
        ),
        "suffix": (
            "Clear manga panel composition, vivid full color, readable silhouettes, "
            "no collage, no extra limbs."
        ),
        "negative_extra": "wrong face, off-model costume, merged characters, blurry faces",
    },
    "seedream": {
        "prefix": (
            "Anime/manga illustration, clean ink linework, strong stylized shading, "
            "shonen panel energy. "
        ),
        "suffix": (
            "Crisp cel-shaded color, expressive eyes, dynamic pose, single panel only, "
            "no photoreal skin texture."
        ),
        "negative_extra": (
            "photoreal, 3d render, muddy lines, western comic style, soft focus"
        ),
    },
    "flux": {
        "prefix": (
            "High-detail illustration with precise lighting and anatomy. "
            "Follow the brief literally. "
        ),
        "suffix": (
            "Sharp edges, coherent hands, consistent outfit colors, manga panel framing."
        ),
        "negative_extra": "deformed hands, text artifacts, watermark, low contrast",
    },
    "generic": {
        "prefix": "",
        "suffix": "Single manga panel, clear character design, match references.",
        "negative_extra": "watermark, blurry, extra fingers",
    },
}


def family_for_model(model_id: str | None) -> str:
    mid = (model_id or "").lower()
    for needle, family in MODEL_FAMILY_HINTS:
        if needle in mid:
            return family
    return "generic"


def family_for_profile(profile_id: str | None, settings: dict[str, Any] | None = None) -> str:
    if profile_id and profile_id in PROFILE_FAMILY:
        return PROFILE_FAMILY[profile_id]
    if settings:
        models = settings.get("models") or {}
        chain = []
        profiles = models.get("image_profiles") or {}
        prof = profiles.get(profile_id or models.get("image_profile") or "") or {}
        if isinstance(prof.get("chain"), list) and prof["chain"]:
            chain = prof["chain"]
        elif isinstance(models.get("image_model_chain"), list):
            chain = models["image_model_chain"]
        if chain:
            return family_for_model(str(chain[0]))
    return "generic"


def folder_label_for_family(family: str) -> str:
    return {
        "nano_banana": "Nano Banana",
        "seedream": "Seedream",
        "flux": "FLUX",
        "generic": "Other",
        "mock": "Mock",
        "pollinations": "Pollinations",
    }.get(family, family.replace("_", " ").title())


def folder_label_for_model(model_id: str | None, *, backend: str | None = None) -> str:
    # Prefer the model family when we know which model produced the image
    # (including mock multi-runs that still tag Nano Banana / Seedream / FLUX).
    if model_id:
        return folder_label_for_family(family_for_model(model_id))
    if backend == "mock":
        return folder_label_for_family("mock")
    if backend == "pollinations":
        return folder_label_for_family("pollinations")
    return folder_label_for_family("generic")


def adapt_prompt_for_family(
    prompt: str,
    negative_prompt: str,
    family: str,
) -> tuple[str, str]:
    hints = FAMILY_HINTS.get(family) or FAMILY_HINTS["generic"]
    prefix = hints["prefix"].strip()
    suffix = hints["suffix"].strip()
    parts = [p for p in (prefix, prompt.strip(), suffix) if p]
    adapted = " ".join(parts)
    neg = negative_prompt.strip()
    extra = hints.get("negative_extra") or ""
    if extra and extra.lower() not in neg.lower():
        neg = f"{neg}, {extra}".strip(", ").strip()
    return adapted, neg


def adapt_prompt_for_model(
    prompt: str,
    negative_prompt: str,
    model_id: str | None,
    *,
    backend: str | None = None,
) -> tuple[str, str]:
    if backend == "mock":
        return prompt, negative_prompt
    return adapt_prompt_for_family(prompt, negative_prompt, family_for_model(model_id))


def adapt_prompt_for_settings(
    prompt: str,
    negative_prompt: str,
    settings: dict[str, Any],
) -> tuple[str, str]:
    """Adapt using the user's currently selected image profile (compile-time)."""
    profile = (settings.get("models") or {}).get("image_profile")
    family = family_for_profile(profile, settings)
    return adapt_prompt_for_family(prompt, negative_prompt, family)
