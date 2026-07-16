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
Write in plain prose. Do not use markdown italics, bold, headings, or underscore emphasis.
If RUN CONTEXT is provided, ground answers in it and do not invent facts missing from context.
If comparing plans A and B in context, say which plan you mean.
When no run context is attached, answer helpfully as a general planning assistant.
"""


def default_chat_catalog(settings: dict[str, Any]) -> list[dict[str, str]]:
    """Chat models: each entry may use explicit `model` and/or a role key."""
    configured = settings.get("chat_models")
    role_models: dict[str, str] = settings.get("models") or {}
    out: list[dict[str, str]] = []

    if isinstance(configured, list) and configured:
        for item in configured:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id") or item.get("role") or "").strip()
            if not mid:
                continue
            role = str(item.get("role") or "").strip()
            model = str(item.get("model") or "").strip()
            if not model and role and role in role_models:
                model = role_models[role]
            if not model and mid in role_models:
                model = role_models[mid]
                role = role or mid
            if not model:
                continue
            out.append(
                {
                    "id": mid,
                    "label": str(item.get("label") or mid),
                    "role": role or mid,
                    "model": model,
                }
            )
        if out:
            return out

    labels = {
        "judge": "Claude (Judge)",
        "advocate": "Grok (Advocate)",
        "scout": "GPT-5 mini (Scout)",
        "skeptic": "Gemini (Skeptic)",
        "promoter": "Gemini (Promoter)",
    }
    for role in ("judge", "advocate", "scout", "skeptic", "promoter"):
        if role in role_models:
            out.append(
                {
                    "id": role,
                    "label": labels.get(role, role.title()),
                    "role": role,
                    "model": role_models[role],
                }
            )
    return out


def resolve_model_string(entry: dict[str, str], router: ModelRouter) -> str:
    if entry.get("model"):
        return entry["model"]
    role = entry.get("role") or entry.get("id") or ""
    return router.model_for(role)


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
    pending_question: str | None = None,
) -> dict[str, Any]:
    catalog = {m["id"]: m for m in default_chat_catalog(settings)}
    selected = [catalog[mid] for mid in model_ids if mid in catalog]
    if not selected:
        # Prefer configured default_panel when present
        panel_ids = list((_chat_cfg(settings).get("default_panel") or []))
        selected = [catalog[mid] for mid in panel_ids if mid in catalog]
        if not selected:
            defaults = default_chat_catalog(settings)
            selected = defaults[:3] or [
                {
                    "id": "judge",
                    "label": "Judge",
                    "role": "judge",
                    "model": (settings.get("models") or {}).get(
                        "judge", "openrouter/anthropic/claude-fable-5"
                    ),
                }
            ]

    chat: dict[str, Any] = {
        "id": new_chat_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "models": selected,
        "detail": detail,
        "run_dir": None,
        "run_attached": bool(run_result),
        "messages": [],
        "pending_question": pending_question,
    }
    if run_result:
        chat["run_dir"] = run_result.get("run_dir") or (
            (run_result.get("result_a") or {}).get("run_dir")
        )
        chat["run_context"] = build_run_context(run_result, detail=detail)
        money = run_result.get("money_facts") or (
            (run_result.get("result_a") or {}).get("money_facts")
        )
        if money:
            chat["money_facts"] = money
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
            content = msg.get("content")
            if content:
                messages.append({"role": "assistant", "content": str(content)})
            elif isinstance(msg.get("replies"), dict):
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


def _call_one(
    router: ModelRouter,
    model: dict[str, str],
    messages: list[dict[str, str]],
    *,
    temperature: float,
) -> str:
    mid = model["id"]
    litellm_model = resolve_model_string(model, router)
    fallback = None
    role = model.get("role") or ""
    if role and role in (router.fallbacks or {}):
        fallback = router.fallbacks[role]
    return router.complete_model_messages(
        litellm_model,
        messages,
        label=mid,
        fallback=fallback,
        temperature=temperature,
        max_tokens=900,
    )


def _stream_one(
    router: ModelRouter,
    model: dict[str, str],
    messages: list[dict[str, str]],
    *,
    temperature: float,
) -> Iterator[str]:
    mid = model["id"]
    litellm_model = resolve_model_string(model, router)
    fallback = None
    role = model.get("role") or ""
    if role and role in (router.fallbacks or {}):
        fallback = router.fallbacks[role]
    yield from router.complete_model_messages_stream(
        litellm_model,
        messages,
        label=mid,
        fallback=fallback,
        temperature=temperature,
        max_tokens=900,
    )


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
        history = _history_for_model(chat, mid)
        messages = _build_messages(chat, history, question)
        try:
            text = _call_one(router, model, messages, temperature=temperature)
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
        history = _history_for_model(chat, mid)
        messages = _build_messages(chat, history, question)
        try:
            for chunk in _stream_one(router, model, messages, temperature=temperature):
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
    *,
    consensus: str | None = None,
    next_question: str | None = None,
    qa_notes: str | None = None,
    qa_verdict: str | None = None,
) -> dict[str, Any]:
    chat.setdefault("messages", []).append(
        {"role": "user", "content": question, "ts": datetime.now(timezone.utc).isoformat()}
    )
    assistant: dict[str, Any] = {
        "role": "assistant",
        "content": consensus or "",
        "replies": replies,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if next_question:
        assistant["next_question"] = next_question
    if qa_notes:
        assistant["qa_notes"] = qa_notes
    if qa_verdict:
        assistant["qa_verdict"] = qa_verdict
    chat["messages"].append(assistant)
    if next_question:
        chat["pending_question"] = next_question
    chat["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_chat(settings, chat)
    return chat


def label_for(chat: dict[str, Any], model_id: str) -> str:
    for m in chat.get("models") or []:
        if m.get("id") == model_id:
            return str(m.get("label") or model_id)
    return model_id


CONSENSUS_SYSTEM = """You synthesize multiple model drafts into ONE clear consensus answer.
Rules:
- Write plain prose only. No markdown, no italics, no headings, no bullet symbols if you can avoid them.
- Prefer facts from RUN CONTEXT. Never invent numbers. If VERIFIED MONEY MATH exists, use those figures exactly.
- Where drafts disagree, say what the consensus is and briefly note the disagreement.
- Keep it short and decisive unless the user asked for detail.
- End without asking a question (a separate step will ask the user).
"""

QA_SYSTEM = """You are Verdict Loop's fact-check auditor (QA).
You receive RUN CONTEXT, the USER QUESTION, a DRAFT consensus answer, and possibly
DETERMINISTIC CHECK FAILURES from a calculator that has already verified the math.
Your job: catch invented facts, wrong money math, and claims not supported by context.

Respond with ONLY a JSON object, no code fences, in this exact shape:
{"verdict": "PASS" or "REVISE", "issues": ["short issue", ...] or [], "answer": "final answer text"}

Rules:
- If DETERMINISTIC CHECK FAILURES are listed, verdict MUST be REVISE and the answer
  must be rewritten so every figure matches the VERIFIED MONEY MATH in context.
- If VERIFIED MONEY MATH is present, numbers in the answer must match it exactly.
- If a claim is not supported by RUN CONTEXT and is not common knowledge, flag it.
- If something is unknown, the answer should say what is missing instead of guessing.
- The answer must be plain prose. No markdown, no headings, no bullet symbols.
- When unsure, prefer REVISE over PASS.
"""

NEXT_Q_SYSTEM = """You ask the user ONE clarifying follow-up question.
It should help resolve the biggest remaining uncertainty in the verdict.
Plain text only — just the question, nothing else. No markdown.
"""


def _chat_cfg(settings: dict[str, Any]) -> dict[str, Any]:
    cfg = settings.get("chat") or {}
    return cfg if isinstance(cfg, dict) else {}


def _panel_models(
    chat: dict[str, Any],
    settings: dict[str, Any],
    model_ids: list[str] | None,
) -> list[dict[str, str]]:
    selected = chat.get("models") or []
    if model_ids:
        id_set = set(model_ids)
        selected = [m for m in selected if m["id"] in id_set]
    max_panel = int(_chat_cfg(settings).get("max_panel") or 3)
    return selected[: max(1, max_panel)]


def ask_consensus(
    router: ModelRouter,
    settings: dict[str, Any],
    chat: dict[str, Any],
    question: str,
    *,
    model_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Panel models draft in parallel → synthesizer consensus → QA audit → next user question.
    Returns {replies, consensus, qa_notes, next_question, qa_verdict}.
    """
    panel = _panel_models(chat, settings, model_ids)
    cfg = _chat_cfg(settings)
    synth_model = str(
        cfg.get("synthesizer")
        or (settings.get("models") or {}).get("judge")
        or "openrouter/anthropic/claude-fable-5"
    )
    qa_model = str(
        cfg.get("qa_model")
        or (settings.get("models") or {}).get("qa")
        or "openrouter/openai/o3"
    )

    # 1) Panel drafts
    replies = ask_models(router, chat, question, model_ids=[m["id"] for m in panel])

    # 2) Consensus
    draft_block = "\n\n".join(
        f"[{label_for(chat, mid)}]:\n{text}" for mid, text in replies.items()
    )
    ctx = chat.get("run_context") or "(no run context)"
    synth_messages = [
        {"role": "system", "content": CONSENSUS_SYSTEM},
        {
            "role": "user",
            "content": (
                f"RUN CONTEXT:\n{ctx}\n\n"
                f"USER QUESTION:\n{question}\n\n"
                f"MODEL DRAFTS:\n{draft_block}\n\n"
                "Write the single consensus answer now."
            ),
        },
    ]
    try:
        draft = router.complete_model_messages(
            synth_model,
            synth_messages,
            label="synthesizer",
            temperature=0.2,
            max_tokens=900,
        )
    except Exception as exc:
        # Fall back to first non-error draft
        draft = next(
            (t for t in replies.values() if not str(t).startswith("Error:")),
            f"Could not build consensus: {exc}",
        )

    # 3) Deterministic money gate on the draft
    from harness.money import check_draft_numbers

    money_facts = chat.get("money_facts")
    gate_issues = check_draft_numbers(draft, money_facts)

    # 4) QA audit (different model family), structured JSON output
    gate_block = ""
    if gate_issues:
        gate_block = "\n\nDETERMINISTIC CHECK FAILURES:\n" + "\n".join(
            f"- {i}" for i in gate_issues
        )
    qa_messages = [
        {"role": "system", "content": QA_SYSTEM},
        {
            "role": "user",
            "content": (
                f"RUN CONTEXT:\n{ctx}\n\n"
                f"USER QUESTION:\n{question}\n\n"
                f"DRAFT:\n{draft}"
                f"{gate_block}"
            ),
        },
    ]
    qa_notes = "none"
    qa_verdict = "PASS"
    consensus = draft
    try:
        qa_raw = router.complete_model_messages(
            qa_model,
            qa_messages,
            label="qa",
            fallback=(router.fallbacks or {}).get("qa"),
            temperature=0.1,
            max_tokens=900,
        )
        qa_verdict, qa_notes, consensus = _parse_qa_block(qa_raw, draft)
    except Exception as exc:
        qa_notes = f"QA audit unavailable ({exc})"
        consensus = draft
        if gate_issues:
            qa_verdict = "REVISE"

    # 5) Re-run the gate on whatever answer survived QA; fail closed.
    final_gate = check_draft_numbers(consensus, money_facts)
    if final_gate:
        qa_verdict = "REVISE"
        gate_note = "; ".join(final_gate)
        qa_notes = gate_note if qa_notes in ("none", "") else f"{qa_notes}; {gate_note}"
    elif gate_issues and qa_verdict == "PASS":
        # QA fixed the numbers but forgot to flag it — keep the audit trail honest.
        qa_verdict = "REVISE"
        qa_notes = "; ".join(gate_issues)

    # 4) Next question for the user
    next_q = ""
    try:
        nq_messages = [
            {"role": "system", "content": NEXT_Q_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"RUN CONTEXT:\n{ctx}\n\n"
                    f"USER just said/asked:\n{question}\n\n"
                    f"CONSENSUS ANSWER we gave them:\n{consensus}\n\n"
                    "Ask one sharp follow-up question."
                ),
            },
        ]
        next_q = router.complete_model_messages(
            synth_model,
            nq_messages,
            label="next_question",
            temperature=0.4,
            max_tokens=120,
        ).strip()
        next_q = next_q.split("\n")[0].strip().strip('"')
    except Exception:
        next_q = "What else do you need clarified before you decide?"

    return {
        "replies": replies,
        "consensus": consensus,
        "qa_notes": qa_notes,
        "qa_verdict": qa_verdict,
        "next_question": next_q,
    }


def _parse_qa_block(qa_raw: str, draft: str) -> tuple[str, str, str]:
    """Parse the QA model's JSON audit. Falls back to legacy VERDICT/ISSUES/ANSWER
    lines, and fails closed (REVISE) when the output is unparseable."""
    text = qa_raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            data = None
        if isinstance(data, dict):
            verdict = "REVISE" if str(data.get("verdict", "")).strip().upper() != "PASS" else "PASS"
            raw_issues = data.get("issues") or []
            if isinstance(raw_issues, str):
                raw_issues = [raw_issues] if raw_issues.strip() else []
            issues = "; ".join(str(i) for i in raw_issues if str(i).strip()) or "none"
            answer = str(data.get("answer") or "").strip()
            return verdict, issues, answer or draft

    # Legacy plain-text shape
    verdict = ""
    issues = "none"
    answer = ""
    for line in qa_raw.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("VERDICT:"):
            verdict = "REVISE" if "REVISE" in upper else "PASS"
        elif upper.startswith("ISSUES:"):
            issues = stripped.split(":", 1)[-1].strip() or "none"
    for marker in ("ANSWER:", "Answer:", "answer:"):
        idx = qa_raw.find(marker)
        if idx >= 0:
            answer = qa_raw[idx + len(marker) :].strip()
            break
    if not verdict:
        # Could not understand the audit at all — fail closed on the draft.
        return "REVISE", "QA output was unparseable; showing unaudited draft.", draft
    return verdict, issues, answer or draft
