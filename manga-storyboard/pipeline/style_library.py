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


def resolve_ref_path(ref_name: str | None) -> Path | None:
    """Resolve a ref (original filename, stored filename, or character name) to an image path."""
    if not ref_name:
        return None
    key = str(ref_name).strip().lower()
    items = load_library()
    for item in items:
        if (item.get("original_name") or "").lower() == key or (item.get("filename") or "").lower() == key:
            path = Path(item["path"])
            return path if path.exists() else None
    for item in items:
        if (item.get("character") or "").strip().lower() == key:
            path = Path(item["path"])
            return path if path.exists() else None
    return None


# ---------- Persistent character map (survives refresh) ----------

CHARACTERS_NAME = "characters.json"


def _characters_path() -> Path:
    return library_dir() / CHARACTERS_NAME


def load_character_map() -> list[dict[str, Any]]:
    """Saved character -> {look, ref} mappings, remembered across sessions."""
    path = _characters_path()
    if not path.exists():
        return []
    try:
        data = load_json(path)
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def save_character_map(maps: list[dict[str, Any]]) -> None:
    clean = []
    seen = set()
    for row in maps:
        name = (row.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        clean.append(
            {
                "name": name,
                "look": (row.get("look") or "").strip(),
                "ref": row.get("ref") or None,
            }
        )
    save_json(_characters_path(), clean)


def upsert_character(name: str, *, look: str = "", ref: str | None = None) -> None:
    name = (name or "").strip()
    if not name:
        return
    maps = load_character_map()
    for row in maps:
        if (row.get("name") or "").strip().lower() == name.lower():
            if look:
                row["look"] = look
            if ref:
                row["ref"] = ref
            save_character_map(maps)
            return
    maps.append({"name": name, "look": look, "ref": ref})
    save_character_map(maps)


def merge_saved_characters(maps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlay saved character mappings onto analysis-derived maps.

    Saved refs/looks win when the analysis has none; saved characters missing
    from the analysis are appended so recurring cast is never lost on refresh.
    """
    saved = {(r.get("name") or "").strip().lower(): r for r in load_character_map()}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in maps:
        name = (row.get("name") or "").strip()
        key = name.lower()
        seen.add(key)
        hit = saved.get(key)
        if hit:
            row = {
                "name": name,
                "look": row.get("look") or hit.get("look") or "",
                "ref": row.get("ref") or hit.get("ref"),
            }
        out.append(row)
    for key, hit in saved.items():
        if key not in seen:
            out.append({"name": hit.get("name"), "look": hit.get("look", ""), "ref": hit.get("ref")})
    return out
