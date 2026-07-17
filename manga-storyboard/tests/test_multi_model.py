"""Multi-model generation (Nano Banana + Seedream + …)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.generate import generate_panel_image, load_variants_sidecar
from pipeline.image_catalog import model_slug, run_mode, selected_model_ids
from pipeline.util import load_settings


def test_run_mode_and_selected():
    settings = {
        "models": {
            "image_run_mode": "all_selected",
            "image_models_selected": [
                "google/gemini-3-pro-image",
                "bytedance-seed/seedream-4.5",
            ],
        }
    }
    assert run_mode(settings) == "all_selected"
    assert selected_model_ids(settings) == [
        "google/gemini-3-pro-image",
        "bytedance-seed/seedream-4.5",
    ]


def test_model_slug():
    assert model_slug("bytedance-seed/seedream-4.5") == "seedream"
    assert model_slug("google/gemini-3-pro-image") == "nano_banana"
    assert model_slug("black-forest-labs/flux.2-pro") == "flux"


def test_multi_model_mock_writes_variants(tmp_path, monkeypatch):
    monkeypatch.setenv("MANGA_MOCK_IMAGES", "1")
    monkeypatch.setenv("MANGA_DESKTOP_EXPORT_DIR", str(tmp_path / "desk"))
    settings = load_settings()
    settings["models"]["image_backend"] = "mock"
    settings["models"]["image_run_mode"] = "all_selected"
    settings["models"]["image_models_selected"] = [
        "google/gemini-3-pro-image",
        "bytedance-seed/seedream-4.5",
        "black-forest-labs/flux.2-pro",
    ]
    out = tmp_path / "panel_001_a0.png"
    generate_panel_image(settings, "Kaito on a rooftop", "watermark", out)
    assert out.exists()
    nano = tmp_path / "panel_001_a0__nano_banana.png"
    seed = tmp_path / "panel_001_a0__seedream.png"
    flux = tmp_path / "panel_001_a0__flux.png"
    assert nano.exists() and seed.exists() and flux.exists()
    variants = load_variants_sidecar(out)
    assert len(variants) == 3
    assert all(v["ok"] for v in variants)
    # Desktop got a copy under each model family folder
    desk = tmp_path / "desk"
    assert (desk / "Nano Banana").is_dir()
    assert (desk / "Seedream").is_dir()
    assert (desk / "FLUX").is_dir()
    assert any((desk / "Nano Banana").glob("*.png"))
    assert any((desk / "Seedream").glob("*.png"))
    assert any((desk / "FLUX").glob("*.png"))
    # Sidecar is valid JSON
    side = out.with_name(out.stem + ".variants.json")
    data = json.loads(side.read_text(encoding="utf-8"))
    assert data["primary_model"] == "google/gemini-3-pro-image"
