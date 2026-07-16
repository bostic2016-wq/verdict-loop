#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from harness.config import ROOT, load_settings
from harness.followup import answer_followup, append_followup, suggested_followups
from harness.pipeline import run_compare, run_pipeline
from harness.router import ModelRouter
from harness.templates import TEMPLATES

app = FastAPI(title="Verdict Loop v3")
templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))

outputs_root = ROOT / "outputs"
outputs_root.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_root)), name="outputs")
app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")

# Simple in-memory store for FastAPI follow-ups (local use)
_LAST: dict = {"result": None, "messages": []}


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

    _LAST["result"] = result
    _LAST["messages"] = []
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


@app.get("/health")
async def health():
    return {"ok": True, "version": "v3"}


def main() -> None:
    import uvicorn

    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
