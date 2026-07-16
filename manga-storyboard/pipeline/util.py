"""Shared helpers: config, JSON parsing, paths."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

SECRET_KEYS = (
    "OPENROUTER_API_KEY",
    "FAL_KEY",
    "REPLICATE_API_TOKEN",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "APP_PASSWORD",
)


def _apply_streamlit_secrets() -> None:
    """Load Streamlit Cloud secrets into env (does not override existing env)."""
    try:
        import streamlit as st

        secrets = getattr(st, "secrets", None)
        if secrets is None:
            return
        for key in SECRET_KEYS:
            if key in os.environ and os.environ[key]:
                continue
            try:
                val = secrets.get(key) if hasattr(secrets, "get") else secrets[key]
            except Exception:  # noqa: BLE001
                continue
            if val:
                os.environ[key] = str(val)
    except Exception:  # noqa: BLE001
        return


def load_settings() -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    _apply_streamlit_secrets()
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_style(style_id: str) -> dict[str, Any]:
    settings = load_settings()
    styles_dir = ROOT / settings["paths"]["styles_dir"]
    path = styles_dir / f"{style_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Style preset not found: {style_id}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_styles() -> list[dict[str, Any]]:
    settings = load_settings()
    styles_dir = ROOT / settings["paths"]["styles_dir"]
    out = []
    for path in sorted(styles_dir.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        out.append({"id": data.get("id", path.stem), "name": data.get("name", path.stem), "path": str(path)})
    return out


def parse_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty JSON response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return json.loads(match.group(1).strip())
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def new_run_dir() -> Path:
    settings = load_settings()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{stamp}_{uuid.uuid4().hex[:6]}"
    path = ROOT / settings["paths"]["outputs_dir"] / run_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "panels").mkdir(exist_ok=True)
    return path


def library_dir() -> Path:
    settings = load_settings()
    path = ROOT / settings["paths"]["library_dir"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
