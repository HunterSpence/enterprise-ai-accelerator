"""
CloudIQ — AI Architecture Analyzer
FastAPI web app: paste AWS config / Terraform / description → get analysis
Run: uvicorn app:app --reload --port 8001
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from analyzer import CloudIQAnalyzer

load_dotenv()

app = FastAPI(title="CloudIQ — AI Architecture Analyzer", version="1.0.0")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_analyzer = None


def get_analyzer() -> CloudIQAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = CloudIQAnalyzer()
    return _analyzer


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "result": None,
        "error": None,
        "input_text": "",
    })


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, config_input: str = Form(...)):
    result = None
    error = None

    if not config_input.strip():
        error = "Please paste a cloud configuration or architecture description."
    else:
        try:
            analyzer = get_analyzer()
            result = analyzer.analyze(config_input)
        except Exception as exc:
            error = f"Analysis failed: {exc}"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "result": result,
        "error": error,
        "input_text": config_input,
    })


@app.get("/health")
async def health():
    return {"status": "ok", "module": "cloudiq"}
