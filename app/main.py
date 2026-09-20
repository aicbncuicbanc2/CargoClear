"""FastAPI app: the three report screens over the pipeline's output.

The pipeline reads ~250 attachments and may consult Gemini for the
ambiguous ~4% of emails, so it runs once and the results are held in a
module-level cache. Rebuilding per request would make every page load wait
on file I/O and network calls.

The cache is populated lazily on the first request rather than at import
time, so that importing this module (tests, `--reload` workers, the
container's health probe) stays instant.
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.pipeline.models import COMPARISON_FIELDS, Category, Status
from app.pipeline.pipeline import DEFAULT_SOURCE, ProcessedEmail, process_inbox

APP_DIR = Path(__file__).parent

app = FastAPI(title="Shipping Document Verification")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")

# email_id -> ProcessedEmail. Populated once, under a lock so two concurrent
# first requests cannot both pay for a full inbox run.
_REPORTS: dict[str, ProcessedEmail] = {}
_REPORTS_LOCK = Lock()

# Maps a verdict to the badge classes already defined in base.html:
# green=match, red=mismatch, amber=needs review, gray=not a comparison.
STATUS_BADGES = {
    Status.OK.value: "badge-match",
    Status.MISMATCH.value: "badge-mismatch",
    Status.NEEDS_REVIEW.value: "badge-review",
}


def status_badge(status: str, category: str) -> str:
    """Badge class for a row.

    A non-comparison email is gray rather than green: its OK status means
    "no comparison was requested", not "the documents agree", and colouring
    those green would overstate what the pipeline actually checked.
    """
    if category != Category.BL_COMPARISON.value:
        return "badge-na"
    return STATUS_BADGES.get(status, "badge-na")


def get_reports(refresh: bool = False) -> dict[str, ProcessedEmail]:
    """The cached pipeline output for the whole inbox."""
    global _REPORTS
    with _REPORTS_LOCK:
        if refresh or not _REPORTS:
            _REPORTS = process_inbox(DEFAULT_SOURCE)
        return _REPORTS


def build_stats(reports: dict[str, ProcessedEmail]) -> dict:
    """Header counters for the inbox overview."""
    comparisons = [
        p
        for p in reports.values()
        if p.result.category is Category.BL_COMPARISON
    ]
    return {
        "total": len(reports),
        "comparisons": len(comparisons),
        "mismatches": sum(1 for p in comparisons if p.result.status is Status.MISMATCH),
        "escalated": sum(
            1 for p in comparisons if p.result.status is Status.NEEDS_REVIEW
        ),
    }


def _as_row(processed: ProcessedEmail) -> dict:
    report = processed.report
    result = report.result
    return {
        "email_id": report.email_id,
        "subject": report.subject,
        "sender": report.sender,
        "category": result.category.value,
        "status": result.status.value,
        "review_reason": result.review_reason.value if result.review_reason else None,
        "badge": status_badge(result.status.value, result.category.value),
        "defect_fields": result.defect_fields,
        # The dataset carries no timestamp field (email_id, from, subject,
        # body, attachments), so the table shows attachment count instead —
        # a real per-email fact, and the one that decides whether a
        # comparison was even possible.
        "attachment_count": processed.attachment_count,
    }


@app.get("/", response_class=HTMLResponse)
def inbox_overview(
    request: Request,
    category: str = Query("", description="Filter by category"),
    status: str = Query("", description="Filter by status"),
    q: str = Query("", description="Search email id, subject or sender"),
):
    """Screen 1: table of every processed email + stats header."""
    reports = get_reports()
    stats = build_stats(reports)

    rows = [_as_row(processed) for processed in reports.values()]
    if category:
        rows = [row for row in rows if row["category"] == category]
    if status:
        rows = [row for row in rows if row["status"] == status]
    if q:
        # 520 rows is a lot to scroll to reach one email. Substring over the
        # three fields a user actually knows: the id, the subject, the sender.
        needle = q.strip().casefold()
        rows = [
            row
            for row in rows
            if needle in row["email_id"].casefold()
            or needle in row["subject"].casefold()
            or needle in row["sender"].casefold()
        ]

    return templates.TemplateResponse(
        request,
        "inbox.html",
        {
            "emails": rows,
            "stats": stats,
            "categories": [c.value for c in Category],
            "statuses": [s.value for s in Status],
            "selected_category": category,
            "selected_status": status,
            "query": q,
        },
    )


@app.get("/email/{email_id}", response_class=HTMLResponse)
def email_detail(request: Request, email_id: str):
    """Screen 2: SI vs BL comparison view for one email."""
    reports = get_reports()
    processed = reports.get(email_id)

    if processed is None:
        return templates.TemplateResponse(
            request,
            "email_detail.html",
            {"email_id": email_id, "found": False, "row": None},
            status_code=404,
        )

    report = processed.report
    result = report.result
    return templates.TemplateResponse(
        request,
        "email_detail.html",
        {
            "email_id": email_id,
            "found": True,
            "row": _as_row(processed),
            "is_comparison": result.category is Category.BL_COMPARISON,
            "fields": report.fields,
            "field_order": COMPARISON_FIELDS,
            "evidence": report.evidence,
            "si_excerpt": processed.si_excerpt,
            "bl_excerpt": processed.bl_excerpt,
            "confidence": report.confidence,
            "signals": report.signals,
        },
    )


@app.get("/review", response_class=HTMLResponse)
def review_queue(request: Request):
    """Screen 3: everything escalated to a human."""
    reports = get_reports()
    escalations = [
        {**_as_row(processed), "evidence": processed.report.evidence}
        for processed in reports.values()
        if processed.result.status is Status.NEEDS_REVIEW
    ]
    escalations.sort(key=lambda row: (row["review_reason"] or "", row["email_id"]))
    return templates.TemplateResponse(
        request, "review.html", {"escalations": escalations}
    )


@app.get("/submission.json")
def submission():
    """The graded artifact itself, served from the same cached run the UI shows.

    Built from the cache rather than re-running the pipeline, so what you
    download is exactly the verdict set rendered on the other screens — not a
    second run that could differ on the ~4% of emails Gemini decides.
    """
    reports = get_reports()
    payload = {
        email_id: processed.result.to_submission()
        for email_id, processed in reports.items()
    }
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="submission.json"'},
    )


@app.get("/healthz")
@app.get("/health")
def healthz():
    """Liveness probe, served at two paths.

    Deliberately does not touch the pipeline cache, so it answers instantly
    while the first inbox run is still in flight.

    /health exists because on Cloud Run's *.run.app domains, /healthz is
    swallowed by Google's edge infrastructure and never reaches the
    container: it comes back as a Google HTML 404 with no
    `server: Google Frontend` or `x-cloud-trace-context` header, while an
    unknown path like /nope correctly returns FastAPI's JSON 404. /healthz
    is kept for local runs and any other host; /health is the one to probe
    in production.
    """
    return {"status": "ok"}
