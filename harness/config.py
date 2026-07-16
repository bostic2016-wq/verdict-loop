from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_settings(config_path: Path | None = None) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    path = config_path or (ROOT / "config.yaml")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["_root"] = ROOT
    data["_env"] = {
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY", ""),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
        "POLLINATIONS_API_KEY": os.getenv("POLLINATIONS_API_KEY", ""),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY", ""),
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", ""),
    }
    # LiteLLM reads this env var for openrouter/* models
    if data["_env"]["OPENROUTER_API_KEY"]:
        os.environ["OPENROUTER_API_KEY"] = data["_env"]["OPENROUTER_API_KEY"]
    return data


def require_text_keys(settings: dict[str, Any]) -> None:
    env = settings["_env"]
    if env.get("OPENROUTER_API_KEY"):
        return
    missing = []
    if not env.get("GROQ_API_KEY"):
        missing.append("GROQ_API_KEY")
    if not env.get("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY")
    if missing:
        raise RuntimeError(
            "Missing API keys: "
            + ", ".join(missing)
            + " (or set OPENROUTER_API_KEY). "
            "Copy .env.example to .env and fill them in."
        )
