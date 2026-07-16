"""Style library: save, tag, list user drawings."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from pipeline.util import library_dir, load_json, save_json


META_NAME = "library.json"


def _meta_path() -> Path:
    return library_dir() / META_NAME


def load_library() -> list[dict[str, Any]]:
    path = _meta_path()
    if not path.exists():
        return []
    data = load_json(path)
    return data if isinstance(data, list) else data.get("items", [])


def save_library(items: list[dict[str, Any]]) -> None:
    save_json(_meta_path(), items)


def add_drawing(
    source: Path | bytes,
    *,
    filename: str,
    tags: list[str] | None = None,
    character: str = "",
    notes: str = "",
) -> dict[str, Any]:
    lib = library_dir()
    ext = Path(filename).suffix.lower() or ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        ext = ".png"
    item_id = uuid.uuid4().hex[:10]
    dest_name = f"{item_id}{ext}"
    dest = lib / dest_name
    if isinstance(source, bytes):
        dest.write_bytes(source)
    else:
        shutil.copy2(source, dest)

    item = {
        "id": item_id,
        "filename": dest_name,
        "original_name": filename,
        "tags": tags or [],
        "character": character.strip(),
        "notes": notes.strip(),
        "path": str(dest),
    }
    items = load_library()
    items.append(item)
    save_library(items)
    return item


def remove_drawing(item_id: str) -> bool:
    items = load_library()
    kept = []
    removed = False
    for item in items:
        if item["id"] == item_id:
            path = Path(item["path"])
            if path.exists():
                path.unlink()
            removed = True
        else:
            kept.append(item)
    save_library(kept)
    return removed


def drawings_for_character(character: str) -> list[dict[str, Any]]:
    key = character.strip().lower()
    return [i for i in load_library() if (i.get("character") or "").lower() == key]
