from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).parent

app = FastAPI(title="Shipping Document Verification")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def inbox_overview(request: Request):
    """Screen 1: table of every processed email + stats header."""
    # TODO(Mon 21): wire up real results from the pipeline once
    # classify/extract/compare/escalate are built (Sat-Sun).
    return templates.TemplateResponse(
        request, "inbox.html", {"emails": [], "stats": {}}
    )


@app.get("/email/{email_id}", response_class=HTMLResponse)
def email_detail(request: Request, email_id: str):
    """Screen 2: SI vs BL comparison view for one email."""
    return templates.TemplateResponse(
        request, "email_detail.html", {"email_id": email_id, "result": None}
    )


@app.get("/review", response_class=HTMLResponse)
def review_queue(request: Request):
    """Screen 3: everything escalated to a human."""
    return templates.TemplateResponse(
        request, "review.html", {"escalations": []}
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
