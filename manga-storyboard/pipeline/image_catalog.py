"""Catalog of OpenRouter image models + multi-model run helpers."""

from __future__ import annotations

import os
from typing import Any

# Curated defaults — OpenRouter image models useful for manga storyboards.
# Users can add more via config.yaml image_catalog.
DEFAULT_CATALOG: list[dict[str, str]] = [
    {
        "id": "google/gemini-3-pro-image",
        "label": "Nano Banana Pro",
        "family": "nano_banana",
    },
    {
        "id": "google/gemini-2.5-flash-image-preview",
        "label": "Nano Banana Flash",
        "family": "nano_banana",
    },
    {
        "id": "bytedance-seed/seedream-4.5",
        "label": "Seedream 4.5",
        "family": "seedream",
    },
    {
        "id": "black-forest-labs/flux.2-pro",
        "label": "FLUX.2 Pro",
        "family": "flux",
    },
]


def image_catalog(settings: dict[str, Any]) -> list[dict[str, str]]:
    cfg = (settings.get("models") or {}).get("image_catalog")
    if isinstance(cfg, list) and cfg:
        out = []
        for row in cfg:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            out.append(
                {
                    "id": str(row["id"]),
                    "label": str(row.get("label") or row["id"]),
                    "family": str(row.get("family") or ""),
                }
            )
        return out or list(DEFAULT_CATALOG)
    return list(DEFAULT_CATALOG)


def selected_model_ids(settings: dict[str, Any]) -> list[str]:
    models = settings.get("models") or {}
    selected = models.get("image_models_selected")
    if isinstance(selected, list) and selected:
        return [str(m) for m in selected if m]
    # Fall back to the primary of the active profile chain
    profile = models.get("image_profile")
    profiles = models.get("image_profiles") or {}
    if profile and isinstance(profiles, dict):
        chain = (profiles.get(profile) or {}).get("chain")
        if isinstance(chain, list) and chain:
            return [str(chain[0])]
    chain = models.get("image_model_chain")
    if isinstance(chain, list) and chain:
        return [str(chain[0])]
    return [DEFAULT_CATALOG[0]["id"]]


def run_mode(settings: dict[str, Any]) -> str:
    mode = ((settings.get("models") or {}).get("image_run_mode") or "fallback").strip().lower()
    if mode in {"all", "all_selected", "multi", "compare"}:
        return "all_selected"
    return "fallback"


def model_slug(model_id: str) -> str:
    """Filesystem-safe short name for variant filenames."""
    mid = (model_id or "model").lower()
    if "seedream" in mid or "bytedance" in mid:
        return "seedream"
    if "flux" in mid or "black-forest" in mid:
        return "flux"
    if "gemini" in mid or "nano" in mid or "imagen" in mid:
        if "flash" in mid:
            return "nano_banana_flash"
        return "nano_banana"
    # last path segment, sanitized
    tail = mid.split("/")[-1]
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in tail)[:40]


def fetch_openrouter_image_models(settings: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Optional live catalog from OpenRouter. Falls back to empty on any error."""
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return []
    url = "https://openrouter.ai/api/v1/images/models"
    if settings:
        url = ((settings.get("openrouter") or {}).get("models_url") or url)
    try:
        import httpx

        with httpx.Client(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {key}"})
            if resp.status_code >= 400:
                return []
            data = resp.json()
        rows = data.get("data") or data.get("models") or []
        out: list[dict[str, str]] = []
        for row in rows:
            mid = row.get("id") or row.get("model")
            if not mid:
                continue
            out.append(
                {
                    "id": str(mid),
                    "label": str(row.get("name") or mid),
                    "family": "",
                }
            )
        return out
    except Exception:  # noqa: BLE001
        return []


def merge_catalog_with_live(settings: dict[str, Any]) -> list[dict[str, str]]:
    """Curated catalog first, then any live OpenRouter models not already listed."""
    base = image_catalog(settings)
    seen = {r["id"] for r in base}
    live = fetch_openrouter_image_models(settings)
    for row in live:
        if row["id"] not in seen:
            base.append(row)
            seen.add(row["id"])
    return base
