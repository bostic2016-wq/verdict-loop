"""Panel plan + editorial grammar gate."""

from __future__ import annotations

from typing import Any

from pipeline.roles import GRAMMAR_FIX_SYSTEM, PANEL_PLAN_SYSTEM, PANEL_PLAN_USER
from pipeline.router import DirectorRouter
from pipeline.util import parse_json


VALID_SHOTS = {"wide", "medium", "close", "extreme_close", "ots", "low", "high", "dutch"}


def plan_panels(
    router: DirectorRouter,
    bible: dict[str, Any],
    transcript: str,
    *,
    start_index: int = 1,
    count: int = 5,
) -> list[dict[str, Any]]:
    import json

    raw = router.complete(
        "director",
        PANEL_PLAN_SYSTEM,
        PANEL_PLAN_USER.format(
            bible=json.dumps(bible, indent=2)[:8000],
            transcript=transcript[:40000],
            start_index=start_index,
            count=count,
        ),
        json_mode=True,
        temperature=0.4,
    )
    data = parse_json(raw)
    panels = data.get("panels") or []
    for i, p in enumerate(panels):
        p["index"] = start_index + i
        p.setdefault("id", f"p{p['index']}")
        p.setdefault("shot_type", "medium")
        p.setdefault("dialogue", "")
        p.setdefault("characters", [])
    return validate_and_fix(router, panels)


def validate_grammar(panels: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[str] = []
    if not panels:
        return {"ok": False, "issues": ["No panels planned"]}

    for p in panels:
        if not p.get("action"):
            issues.append(f"Panel {p.get('index')}: missing action beat")
        if not p.get("shot_type") or str(p.get("shot_type")).lower() not in VALID_SHOTS:
            issues.append(f"Panel {p.get('index')}: invalid shot_type")
        if not p.get("subject"):
            issues.append(f"Panel {p.get('index')}: missing subject")

    # No duplicate shots back-to-back
    for i in range(1, len(panels)):
        a = str(panels[i - 1].get("shot_type", "")).lower()
        b = str(panels[i].get("shot_type", "")).lower()
        if a == b == "wide":
            issues.append(f"Panels {panels[i-1].get('index')}-{panels[i].get('index')}: back-to-back wides")
        if a == b == "medium" and len(panels) >= 4:
            # soft issue — only flag if many mediums
            pass

    # Prefer establish before intimate in first two if possible
    if len(panels) >= 2:
        first = str(panels[0].get("shot_type", "")).lower()
        second = str(panels[1].get("shot_type", "")).lower()
        if first in {"extreme_close", "close"} and second == "wide":
            issues.append("Opens on intimate shot before establishing — consider wide first")

    # One idea: action shouldn't contain "and then"
    for p in panels:
        action = (p.get("action") or "").lower()
        if " and then " in action or action.count(" and ") >= 2:
            issues.append(f"Panel {p.get('index')}: likely two beats in one panel")

    return {"ok": len(issues) == 0, "issues": issues}


def validate_and_fix(
    router: DirectorRouter,
    panels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = validate_grammar(panels)
    if result["ok"]:
        return panels

    import json

    raw = router.complete(
        "director",
        GRAMMAR_FIX_SYSTEM,
        (
            "Issues found:\n"
            + "\n".join(f"- {i}" for i in result["issues"])
            + "\n\nCurrent panels JSON:\n"
            + json.dumps({"panels": panels}, indent=2)
            + "\n\nReturn corrected JSON {{\"panels\": [...]}} keeping the same count and indices."
        ),
        json_mode=True,
        temperature=0.3,
    )
    data = parse_json(raw)
    fixed = data.get("panels") or panels
    # Preserve indices
    for i, p in enumerate(fixed):
        if i < len(panels):
            p["index"] = panels[i].get("index", i + 1)
            p.setdefault("id", panels[i].get("id", f"p{p['index']}"))
    return fixed
