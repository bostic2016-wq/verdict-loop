#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from harness.config import ROOT
from harness.pipeline import run_pipeline

app = FastAPI(title="Verdict Loop")
templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))

outputs_root = ROOT / "outputs"
outputs_root.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_root)), name="outputs")
app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"error": None, "result": None},
    )


@app.post("/run", response_class=HTMLResponse)
async def run(
    request: Request,
    claim: str = Form(...),
    with_images: Optional[str] = Form(None),
):
    claim = claim.strip()
    if not claim:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": "Paste a plan or claim first.", "result": None},
            status_code=400,
        )
    try:
        result = run_pipeline(claim, with_images=with_images == "on")
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": str(exc), "result": None},
            status_code=500,
        )

    # Paths relative to outputs/ for the /outputs mount
    run_path = Path(result["run_dir"])
    rel = run_path.relative_to(ROOT / "outputs")
    result["_web_base"] = f"/outputs/{rel.as_posix()}"
    return templates.TemplateResponse(
        request,
        "index.html",
        {"error": None, "result": result},
    )


@app.get("/health")
async def health():
    return {"ok": True}


def main() -> None:
    import uvicorn

    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()