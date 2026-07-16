"""Scout research note schema and helpers."""

from __future__ import annotations

from typing import Any

NOTE_KEYS = (
    "summary",
    "supporting_points",
    "risks",
    "open_questions",
    "assumptions",
)


def empty_notes() -> dict[str, Any]:
    return {
        "summary": "",
        "supporting_points": [],
        "risks": [],
        "open_questions": [],
        "assumptions": [],
    }


def normalize_notes(raw: Any) -> dict[str, Any]:
    """Coerce model output into the Scout schema."""
    if not isinstance(raw, dict):
        notes = empty_notes()
        notes["summary"] = str(raw)
        return notes

    notes = empty_notes()
    notes["summary"] = str(raw.get("summary") or "").strip()

    for key in ("supporting_points", "risks", "open_questions", "assumptions"):
        value = raw.get(key) or []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            value = [str(value)]
        notes[key] = [str(item).strip() for item in value if str(item).strip()]

    # Optional user-pasted context the scout may echo
    if raw.get("user_context"):
        notes["user_context"] = str(raw["user_context"]).strip()

    return notes


def merge_user_context(claim: str, extra_notes: str | None) -> str:
    """Attach optional user-pasted links/notes to the claim for Scout."""
    claim = claim.strip()
    if not extra_notes or not extra_notes.strip():
        return claim
    return (
        f"{claim}\n\nADDITIONAL CONTEXT FROM USER "
        f"(links, notes — treat as source material):\n{extra_notes.strip()}"
    )