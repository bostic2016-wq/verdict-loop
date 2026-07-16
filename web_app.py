#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from harness import __version__
from harness.chat import (
    append_turn,
    ask_models,
    ask_models_events,
    create_chat,
    default_chat_catalog,
    label_for,
    load_chat,
    save_chat,
)
from harness.config import ROOT, load_settings
from harness.followup import answer_followup, append_followup, suggested_followups
from harness.pipeline import run_compare, run_pipeline
from harness.router import ModelRouter
from harness.templates import TEMPLATES

app = FastAPI(title="Verdict Loop v4")
templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))

outputs_root = ROOT / "outputs"
outputs_root.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_root)), name="outputs")
app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")

# In-memory index: run_id / chat_id → payload (also persisted to disk)
_RUNS: dict[str, dict[str, Any]] = {}
_CHATS: dict[str, dict[str, Any]] = {}
# Legacy HTML form session
_LAST: dict = {"result": None, "messages": [], "run_id": None}


def _run_id_from_result(result: dict[str, Any]) -> str:
    run_dir = result.get("run_dir") or (result.get("result_a") or {}).get("run_dir") or ""
    return Path(run_dir).name if run_dir else f"run_{len(_RUNS) + 1}"


def _store_run(result: dict[str, Any]) -> str:
    run_id = _run_id_from_result(result)
    _RUNS[run_id] = result
    return run_id


def _ctx(**extra):
    result = extra.get("result", _LAST.get("result"))
    base = {
        "error": None,
        "result": result,
        "messages": _LAST.get("messages") or [],
        "templates": TEMPLATES,
        "suggestions": suggested_followups(result) if result else [],
        "pick": None,
    }
    base.update(extra)
    if "result" in extra:
        base["suggestions"] = suggested_followups(extra["result"]) if extra["result"] else []
    return base


class ChatCreateBody(BaseModel):
    model_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
    detail: str = "brief"


class ChatMessageBody(BaseModel):
    question: str
    model_ids: list[str] | None = None
    stream: bool = True


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", _ctx())


@app.post("/run", response_class=HTMLResponse)
async def run(
    request: Request,
    mode: str = Form("single"),
    detail: str = Form("brief"),
    claim: str = Form(""),
    claim_a: str = Form(""),
    claim_b: str = Form(""),
    with_images: Optional[str] = Form(None),
):
    detail = "detailed" if detail == "detailed" else "brief"
    mode = (mode or "single").lower()
    try:
        if mode == "compare":
            a, b = claim_a.strip(), claim_b.strip()
            if not a or not b:
                return templates.TemplateResponse(
                    request,
                    "index.html",
                    _ctx(error="Enter both Plan A and Plan B."),
                    status_code=400,
                )
            result = run_compare(a, b, detail=detail)
        else:
            claim = claim.strip()
            if not claim:
                return templates.TemplateResponse(
                    request,
                    "index.html",
                    _ctx(error="Paste a plan or claim first."),
                    status_code=400,
                )
            result = run_pipeline(
                claim,
                with_images=with_images == "on",
                detail=detail,
            )
            run_path = Path(result["run_dir"])
            rel = run_path.relative_to(ROOT / "outputs")
            result["_web_base"] = f"/outputs/{rel.as_posix()}"
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ctx(error=str(exc)),
            status_code=500,
        )

    run_id = _store_run(result)
    _LAST["result"] = result
    _LAST["messages"] = []
    _LAST["run_id"] = run_id
    return templates.TemplateResponse(request, "index.html", _ctx(result=result))


@app.post("/followup", response_class=HTMLResponse)
async def followup(request: Request, question: str = Form(...)):
    result = _LAST.get("result")
    if not result:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ctx(error="Run a verdict first, then ask a follow-up."),
            status_code=400,
        )
    question = question.strip()
    if not question:
        return templates.TemplateResponse(
            request,
            "index.html",
            _ctx(error="Type a follow-up question."),
            status_code=400,
        )
    messages = list(_LAST.get("messages") or [])
    try:
        router = ModelRouter(load_settings())
        answer = answer_followup(
            router,
            result,
            question,
            messages,
            detail=result.get("detail") or "brief",
        )
    except Exception as exc:
        answer = f"Couldn’t answer that follow-up: {exc}"
    messages.append({"role": "user", "content": question})
    messages.append({"role": "assistant", "content": answer})
    _LAST["messages"] = messages
    run_dir = result.get("run_dir") or (result.get("result_a") or {}).get("run_dir")
    if run_dir:
        try:
            append_followup(run_dir, question, answer)
        except Exception:
            pass
    return templates.TemplateResponse(request, "index.html", _ctx())


# ── v4 JSON / SSE API ──────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"ok": True, "version": "v4", "package": __version__}


@app.get("/v4/models")
async def v4_models():
    settings = load_settings()
    return {"models": default_chat_catalog(settings)}


@app.post("/v4/run")
async def v4_run(request: Request):
    body = await request.json()
    mode = str(body.get("mode") or "single").lower()
    detail = "detailed" if body.get("detail") == "detailed" else "brief"
    try:
        if mode == "compare":
            a = str(body.get("claim_a") or "").strip()
            b = str(body.get("claim_b") or "").strip()
            if not a or not b:
                return JSONResponse({"error": "claim_a and claim_b required"}, status_code=400)
            result = run_compare(a, b, detail=detail)
        else:
            claim = str(body.get("claim") or "").strip()
            if not claim:
                return JSONResponse({"error": "claim required"}, status_code=400)
            result = run_pipeline(
                claim,
                with_images=bool(body.get("with_images")),
                detail=detail,
            )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    run_id = _store_run(result)
    _LAST["result"] = result
    _LAST["run_id"] = run_id
    return {"run_id": run_id, "result": result}


@app.get("/v4/runs/{run_id}")
async def v4_get_run(run_id: str):
    result = _RUNS.get(run_id)
    if not result:
        return JSONResponse({"error": "run not found"}, status_code=404)
    return {"run_id": run_id, "result": result}


@app.post("/v4/chat")
async def v4_create_chat(body: ChatCreateBody):
    settings = load_settings()
    run_result = _RUNS.get(body.run_id) if body.run_id else _LAST.get("result")
    chat = create_chat(
        settings,
        model_ids=body.model_ids,
        run_result=run_result,
        detail=body.detail,
    )
    _CHATS[chat["id"]] = chat
    return {"chat": chat}


@app.get("/v4/chat/{chat_id}")
async def v4_get_chat(chat_id: str):
    settings = load_settings()
    chat = _CHATS.get(chat_id) or load_chat(settings, chat_id)
    if not chat:
        return JSONResponse({"error": "chat not found"}, status_code=404)
    _CHATS[chat_id] = chat
    return {"chat": chat}


@app.post("/v4/chat/{chat_id}/message")
async def v4_chat_message(chat_id: str, body: ChatMessageBody):
    settings = load_settings()
    chat = _CHATS.get(chat_id) or load_chat(settings, chat_id)
    if not chat:
        return JSONResponse({"error": "chat not found"}, status_code=404)
    question = body.question.strip()
    if not question:
        return JSONResponse({"error": "question required"}, status_code=400)

    router = ModelRouter(settings)

    if not body.stream:
        replies = ask_models(router, chat, question, model_ids=body.model_ids)
        chat = append_turn(settings, chat, question, replies)
        _CHATS[chat_id] = chat
        return {"chat_id": chat_id, "replies": replies, "chat": chat}

    def event_stream():
        buffers: dict[str, str] = {}
        yield f"data: {json.dumps({'event': 'start', 'chat_id': chat_id})}\n\n"
        for event, mid, payload in ask_models_events(
            router, chat, question, model_ids=body.model_ids
        ):
            if event == "chunk":
                buffers[mid] = buffers.get(mid, "") + payload
                yield f"data: {json.dumps({'event': 'chunk', 'model_id': mid, 'text': payload, 'label': label_for(chat, mid)})}\n\n"
            elif event == "error":
                buffers[mid] = f"Error: {payload}"
                yield f"data: {json.dumps({'event': 'error', 'model_id': mid, 'text': payload})}\n\n"
            elif event == "done":
                yield f"data: {json.dumps({'event': 'done', 'model_id': mid})}\n\n"
        append_turn(settings, chat, question, buffers)
        _CHATS[chat_id] = chat
        save_chat(settings, chat)
        yield f"data: {json.dumps({'event': 'turn_complete', 'replies': buffers})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def main() -> None:
    import uvicorn

    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
