"""Model-specific prompts + Desktop auto-save."""

from __future__ import annotations

from pathlib import Path

from pipeline.desktop_export import ensure_model_folders, save_image_to_desktop
from pipeline.model_prompts import (
    adapt_prompt_for_model,
    adapt_prompt_for_settings,
    family_for_model,
    folder_label_for_model,
)


def test_family_for_model():
    assert family_for_model("bytedance-seed/seedream-4.5") == "seedream"
    assert family_for_model("google/gemini-3-pro-image") == "nano_banana"
    assert family_for_model("black-forest-labs/flux.2-pro") == "flux"


def test_folder_labels():
    assert folder_label_for_model("bytedance-seed/seedream-4.5") == "Seedream"
    assert folder_label_for_model("google/gemini-3-pro-image") == "Nano Banana"
    assert folder_label_for_model(None, backend="mock") == "Mock"


def test_adapt_prompt_seedream_vs_nano():
    base = "Kaito stands on a rooftop"
    neg = "watermark"
    s_prompt, s_neg = adapt_prompt_for_model(base, neg, "bytedance-seed/seedream-4.5")
    n_prompt, n_neg = adapt_prompt_for_model(base, neg, "google/gemini-3-pro-image")
    assert "Anime/manga" in s_prompt or "anime" in s_prompt.lower()
    assert "reference" in n_prompt.lower() or "Photoreal" in n_prompt
    assert s_prompt != n_prompt
    assert "photoreal" in s_neg.lower()
    assert "wrong face" in n_neg.lower() or "off-model" in n_neg.lower()


def test_adapt_prompt_for_settings_uses_profile():
    settings = {"models": {"image_profile": "anime_seedream"}}
    prompt, _ = adapt_prompt_for_settings("panel beat", "", settings)
    assert "Anime" in prompt or "anime" in prompt.lower() or "shonen" in prompt.lower()


def test_desktop_save_goes_to_model_folder(tmp_path):
    src = tmp_path / "panel_003.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    root = tmp_path / "DesktopRoot"
    ensure_model_folders(root)
    dest = save_image_to_desktop(
        src,
        model_id="bytedance-seed/seedream-4.5",
        panel_index=3,
        root=root,
    )
    assert dest is not None
    assert dest.parent.name == "Seedream"
    assert dest.exists()
    assert "_p003" in dest.name

    dest2 = save_image_to_desktop(
        src,
        model_id="google/gemini-3-pro-image",
        panel_index=1,
        root=root,
    )
    assert dest2 is not None
    assert dest2.parent.name == "Nano Banana"
