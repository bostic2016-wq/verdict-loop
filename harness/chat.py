"""v4 multi-model chat: parallel fan-out, optional run grounding, disk persistence."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.followup import build_run_context
from harness.router import ModelRouter

CHAT_SYSTEM = """You are a Verdict Loop chat assistant.
Be clear and concise unless the user asks for detail.
If RUN CONTEXT is provided, ground answers in it and do not invent facts missing from context.
If comparing plans A and B in context, say which plan you mean.
When no run context is attached, answer helpfully as a general planning assistant.
"""


def default_chat_catalog(settings: dict[str, Any]) -> list[dict[str, str]]:
    """Role-backed chat models (label + role id)."""
    configured = settings.get("chat_models")
    if isinstance(configured, list) and configured:
        out: list[dict[str, str]] = []
        for item in configured:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or item.get("id") or "").strip()
            if not role:
                continue
            out.append(
                {
                    "id": str(item.get("id") or role),
                    "label": str(item.get("label") or role),
                    "role": role,
                }
            )
        if out:
            return out

    models = settings.get("models") or {}
    labels = {
        "judge": "Claude (Judge)",
        "advocate": "Grok (Advocate)",
        "scout": "GPT-5 mini (Scout)",
        "skeptic": "Gemini (Skeptic)",
        "promoter": "Gemini (Promoter)",
    }
    catalog: list[dict[str, str]] = []
    for role in ("judge", "advocate", "scout", "skeptic", "promoter"):
        if role in models:
            catalog.append(
                {"id": role, "label": labels.get(role, role.title()), "role": role}
            )
    return catalog


def _chats_root(settings: dict[str, Any]) -> Path:
    root: Path = settings["_root"]
    path = root / "outputs" / "chats"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_chat_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def chat_path(settings: dict[str, Any], chat_id: str) -> Path:
    return _chats_root(settings) / f"{chat_id}.json"


def load_chat(settings: dict[str, Any], chat_id: str) -> dict[str, Any] | None:
    path = chat_path(settings, chat_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save_chat(settings: dict[str, Any], chat: dict[str, Any]) -> Path:
    chat_id = chat["id"]
    path = chat_path(settings, chat_id)
    path.write_text(json.dumps(chat, indent=2), encoding="utf-8")
    return path


def create_chat(
    settings: dict[str, Any],
    *,
    model_ids: list[str],
    run_result: dict[str, Any] | None = None,
    detail: str = "brief",
) -> dict[str, Any]:
    catalog = {m["id"]: m for m in default_chat_catalog(settings)}
    selected = [catalog[mid] for mid in model_ids if mid in catalog]
    if not selected:
        # fall back to first two (or one)
        defaults = default_chat_catalog(settings)[:2]
        selected = defaults or [{"id": "judge", "label": "Judge", "role": "judge"}]

    chat: dict[str, Any] = {
        "id": new_chat_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "models": selected,
        "detail": detail,
        "run_dir": None,
        "run_attached": bool(run_result),
        "messages": [],
    }
    if run_result:
        chat["run_dir"] = run_result.get("run_dir") or (
            (run_result.get("result_a") or {}).get("run_dir")
        )
        chat["run_context"] = build_run_context(run_result, detail=detail)
    save_chat(settings, chat)
    return chat


def _build_messages(
    chat: dict[str, Any],
    history: list[dict[str, Any]],
    question: str,
) -> list[dict[str, str]]:
    system = CHAT_SYSTEM
    ctx = chat.get("run_context")
    if ctx:
        system += f"\n\nRUN CONTEXT:\n{ctx}"

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for msg in history[-12:]:
        role = msg.get("role")
        if role == "user":
            messages.append({"role": "user", "content": str(msg.get("content") or "")})
        elif role == "assistant":
            # Prefer the reply for the model we're about to call if present
            content = msg.get("content")
            if content:
                messages.append({"role": "assistant", "content": str(content)})
            elif isinstance(msg.get("replies"), dict):
                # Flatten a short synthesis of prior multi-replies
                parts = []
                for label, text in msg["replies"].items():
                    parts.append(f"[{label}]: {text}")
                if parts:
                    messages.append(
                        {"role": "assistant", "content": "\n\n".join(parts)[:4000]}
                    )
    messages.append({"role": "user", "content": question.strip()})
    return messages


def _history_for_model(
    chat: dict[str, Any], model_id: str
) -> list[dict[str, Any]]:
    """Collapse multi-reply turns into a single assistant message for one model."""
    history: list[dict[str, Any]] = []
    for msg in chat.get("messages") or []:
        role = msg.get("role")
        if role == "user":
            history.append({"role": "user", "content": msg.get("content") or ""})
        elif role == "assistant":
            replies = msg.get("replies") or {}
            text = replies.get(model_id) or msg.get("content") or ""
            if text:
                history.append({"role": "assistant", "content": text})
    return history


def ask_models(
    router: ModelRouter,
    chat: dict[str, Any],
    question: str,
    *,
    model_ids: list[str] | None = None,
    temperature: float = 0.4,
) -> dict[str, str]:
    """Blocking parallel fan-out. Returns {model_id: answer}."""
    selected = chat.get("models") or []
    if model_ids:
        id_set = set(model_ids)
        selected = [m for m in selected if m["id"] in id_set]
    if not selected:
        selected = chat.get("models") or []

    replies: dict[str, str] = {}

    def _one(model: dict[str, str]) -> tuple[str, str]:
        mid = model["id"]
        role = model["role"]
        history = _history_for_model(chat, mid)
        messages = _build_messages(chat, history, question)
        try:
            text = router.complete_messages(
                role, messages, temperature=temperature, max_tokens=900
            )
        except Exception as exc:
            text = f"Error: {exc}"
        return mid, text

    with ThreadPoolExecutor(max_workers=max(1, len(selected))) as pool:
        futures = [pool.submit(_one, m) for m in selected]
        for fut in as_completed(futures):
            mid, text = fut.result()
            replies[mid] = text

    return replies


def ask_models_events(
    router: ModelRouter,
    chat: dict[str, Any],
    question: str,
    *,
    model_ids: list[str] | None = None,
    temperature: float = 0.4,
) -> Iterator[tuple[str, str, str]]:
    """
    Parallel streaming fan-out.
    Yields (event, model_id, payload) where event is chunk|done|error.
    """
    selected = chat.get("models") or []
    if model_ids:
        id_set = set(model_ids)
        selected = [m for m in selected if m["id"] in id_set]
    if not selected:
        selected = chat.get("models") or []

    q: queue.Queue[tuple[str, str, str]] = queue.Queue()

    def _worker(model: dict[str, str]) -> None:
        mid = model["id"]
        role = model["role"]
        history = _history_for_model(chat, mid)
        messages = _build_messages(chat, history, question)
        try:
            for chunk in router.complete_messages_stream(
                role, messages, temperature=temperature, max_tokens=900
            ):
                q.put(("chunk", mid, chunk))
            q.put(("done", mid, ""))
        except Exception as exc:
            q.put(("error", mid, str(exc)))

    threads = [
        threading.Thread(target=_worker, args=(m,), daemon=True) for m in selected
    ]
    for t in threads:
        t.start()

    remaining = {m["id"] for m in selected}
    while remaining:
        event, mid, payload = q.get()
        yield event, mid, payload
        if event in {"done", "error"}:
            remaining.discard(mid)

    for t in threads:
        t.join(timeout=1)


def append_turn(
    settings: dict[str, Any],
    chat: dict[str, Any],
    question: str,
    replies: dict[str, str],
) -> dict[str, Any]:
    chat.setdefault("messages", []).append(
        {"role": "user", "content": question, "ts": datetime.now(timezone.utc).isoformat()}
    )
    chat["messages"].append(
        {
            "role": "assistant",
            "replies": replies,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    chat["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_chat(settings, chat)
    return chat


def label_for(chat: dict[str, Any], model_id: str) -> str:
    for m in chat.get("models") or []:
        if m.get("id") == model_id:
            return str(m.get("label") or model_id)
    return model_id
