"""ZIP export of panels + captions."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


def export_zip(run_dir: Path, panels: list[dict[str, Any]], out_name: str = "storyboard.zip") -> Path:
    out = run_dir / out_name
    captions = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in panels:
            path = Path(p["path"])
            if path.exists():
                arc = f"panels/{path.name}"
                zf.write(path, arcname=arc)
            captions.append(
                {
                    "index": p.get("index"),
                    "shot_type": p.get("shot_type"),
                    "action": p.get("action"),
                    "dialogue": p.get("dialogue"),
                    "emotion": p.get("emotion"),
                    "passed": p.get("passed"),
                    "needs_review": p.get("needs_review"),
                }
            )
        zf.writestr("captions.json", json.dumps(captions, indent=2, ensure_ascii=False))
        brief = run_dir / "bible.json"
        if brief.exists():
            zf.write(brief, arcname="bible.json")
    return out
