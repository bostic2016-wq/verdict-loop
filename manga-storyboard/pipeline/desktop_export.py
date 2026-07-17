"""Auto-save generated panels onto the user's Desktop, grouped by model.

Creates (if missing):
  ~/Desktop/Manga Storyboard/Nano Banana/
  ~/Desktop/Manga Storyboard/Seedream/
  ~/Desktop/Manga Storyboard/FLUX/
  ~/Desktop/Manga Storyboard/Mock/
  ~/Desktop/Manga Storyboard/Pollinations/
  ~/Desktop/Manga Storyboard/Other/
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.model_prompts import folder_label_for_model

DEFAULT_ROOT_NAME = "Manga Storyboard"

ALL_FOLDER_LABELS = (
    "Nano Banana",
    "Seedream",
    "FLUX",
    "Mock",
    "Pollinations",
    "Other",
)


def desktop_root() -> Path:
    override = os.getenv("MANGA_DESKTOP_EXPORT_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    home = Path.home()
    desktop = home / "Desktop"
    if not desktop.is_dir():
        # Some environments use lowercase or localized names
        for candidate in (home / "desktop", home / "Desktop"):
            if candidate.is_dir():
                desktop = candidate
                break
    return desktop / DEFAULT_ROOT_NAME


def ensure_model_folders(root: Path | None = None) -> Path:
    """Create the Manga Storyboard root and every known model subfolder."""
    base = root or desktop_root()
    base.mkdir(parents=True, exist_ok=True)
    for label in ALL_FOLDER_LABELS:
        (base / label).mkdir(parents=True, exist_ok=True)
    return base


def model_folder(
    model_id: str | None = None,
    *,
    backend: str | None = None,
    root: Path | None = None,
) -> Path:
    base = ensure_model_folders(root)
    label = folder_label_for_model(model_id, backend=backend)
    path = base / label
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_enabled(settings: dict[str, Any] | None = None) -> bool:
    if os.getenv("MANGA_DESKTOP_EXPORT") == "0":
        return False
    if settings is not None:
        cfg = settings.get("desktop_export") or {}
        if cfg.get("enabled") is False:
            return False
    return True


def save_image_to_desktop(
    source: Path,
    *,
    model_id: str | None = None,
    backend: str | None = None,
    panel_index: int | None = None,
    settings: dict[str, Any] | None = None,
    root: Path | None = None,
) -> Path | None:
    """Copy a generated image into the Desktop folder for the winning model."""
    if not export_enabled(settings):
        return None
    src = Path(source)
    if not src.exists():
        return None
    dest_dir = model_folder(model_id, backend=backend, root=root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    idx = f"_p{int(panel_index):03d}" if panel_index is not None else ""
    dest = dest_dir / f"{stamp}{idx}{src.suffix or '.png'}"
    # Avoid collisions if two saves land in the same second
    if dest.exists():
        dest = dest_dir / f"{stamp}{idx}_{os.getpid()}{src.suffix or '.png'}"
    shutil.copy2(src, dest)
    return dest
