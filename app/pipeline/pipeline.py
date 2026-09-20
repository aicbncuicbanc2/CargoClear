"""Wires classify -> extract -> compare -> escalate into one verdict per
email, and builds the submission dict for the whole inbox.

Run it:

    python -m app.pipeline.pipeline                  # writes submission.json
    python -m app.pipeline.pipeline --out other.json
    python -m app.pipeline.pipeline --source http://localhost:8080

Only BL_COMPARISON emails carry a document verdict. Everything else is
reported with the default OK/no-defect body, because status/defect_fields
describe a comparison that, for those categories, never happened.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.pipeline import compare as compare_stage
from app.pipeline import escalate as escalate_stage
from app.pipeline.classify import classify_email, matched_signals
from app.pipeline.extract import UnreadableDocument, extract_with_labels, read_document
from app.pipeline.models import (
    COMPARISON_FIELDS,
    Category,
    EmailReport,
    EmailResult,
    ReviewReason,
    Status,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _default_source() -> Path:
    """Where the dataset bundle lives.

    Honours DATASET_SOURCE from the environment (.env locally, a Cloud Run
    env var in the container) so the image can point at a mounted volume
    without a code change; relative values resolve against the repo root.
    """
    configured = settings.dataset_source or "data"
    path = Path(configured)
    return path if path.is_absolute() else REPO_ROOT / configured


DEFAULT_SOURCE = _default_source()


@dataclass
class ProcessedEmail:
    """One email's full pipeline output.

    `report` is the submission-shaped verdict plus per-field evidence.
    The excerpts are raw document text for the UI to show alongside it;
    they live here rather than on EmailReport because that model defines
    the submission contract and is deliberately left untouched.
    """

    report: EmailReport
    si_excerpt: str = ""
    bl_excerpt: str = ""
    # How many files the email actually carried. Shown in the inbox table:
    # the dataset has no timestamp field, so this is the real per-email
    # fact worth surfacing there.
    attachment_count: int = 0

    @property
    def result(self) -> EmailResult:
        return self.report.result


EVIDENCE_LINES = 8


def _read(
    source: Path, attachment: str
) -> tuple[str | None, dict[str, str], dict[str, str], str]:
    """Read one attachment.

    Returns (text, fields, labels, error). text is None and error is
    populated if the document could not be read at all. `labels` records the
    header this document used for each field it carries, for the UI.
    """
    try:
        text = read_document(Path(source) / attachment)
    except UnreadableDocument as exc:
        return None, {}, {}, str(exc)
    fields, labels = extract_with_labels(text)
    return text, fields, labels, ""


def _excerpt(text: str | None, lines: int = EVIDENCE_LINES) -> str:
    """The first few non-empty lines of a document, for display."""
    if not text:
        return ""
    kept = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(kept[:lines])


def _build_evidence(
    reason: ReviewReason | None,
    defects: list[str],
    attachments: list[str],
    bl_text: str | None,
    si_error: str,
    bl_error: str,
    si_fields: dict[str, str],
    bl_fields: dict[str, str],
) -> str:
    """A short, human-readable justification for the verdict.

    The review queue is meant to save a human time, so each entry has to say
    what is wrong and show the bit of the document that proves it.
    """
    if reason is ReviewReason.MISSING_ATTACHMENT:
        if not attachments:
            return "The email asks for a comparison but carries no attachments."
        names = ", ".join(Path(a).name for a in attachments)
        return f"Only one document was attached ({names}); no draft BL to compare against."

    if reason is ReviewReason.UNREADABLE:
        detail = si_error or bl_error
        if detail:
            return f"Document could not be read: {detail}"
        return "Document could not be read."

    if reason is ReviewReason.WRONG_DOC_TYPE:
        header = _excerpt(bl_text, 4)
        return (
            "The second attachment is not a Bill of Lading. Its header reads:\n"
            f"{header}"
        )

    if reason is ReviewReason.MISSING_VALUE:
        blank_si = [f for f in COMPARISON_FIELDS if si_fields.get(f) == ""]
        blank_bl = [f for f in COMPARISON_FIELDS if bl_fields.get(f) == ""]
        parts = []
        if blank_si:
            parts.append(f"left blank in the SI: {', '.join(blank_si)}")
        if blank_bl:
            parts.append(f"left blank in the BL: {', '.join(blank_bl)}")
        if not parts:
            unstated = [
                f
                for f in COMPARISON_FIELDS
                if not si_fields.get(f) or not bl_fields.get(f)
            ]
            parts.append(f"not stated in one of the documents: {', '.join(unstated)}")
        return "Cannot compare — " + "; ".join(parts) + "."

    if defects:
        rows = [
            f"{field}: SI has {si_fields.get(field)!r}, BL has {bl_fields.get(field)!r}"
            for field in defects
        ]
        return "\n".join(rows)

    return "All 7 fields agree between the SI and the draft BL."


def process_email(email: dict, source: Path = DEFAULT_SOURCE) -> ProcessedEmail:
    """Run one email through all four stages."""
    email_id = email.get("email_id", "")
    category, confidence = classify_email(email)

    result = EmailResult(category=category)
    report = EmailReport(
        email_id=email_id,
        subject=email.get("subject", ""),
        sender=email.get("from") or email.get("sender", ""),
        result=result,
        confidence=confidence,
        signals=matched_signals(email, category),
    )

    attachment_count = len(email.get("attachments") or [])

    if category is not Category.BL_COMPARISON:
        return ProcessedEmail(report, attachment_count=attachment_count)

    # A BL_COMPARISON email that never carried documents and never asked for
    # a comparison (91 of them read "please assist to send the draft BL for
    # checking") has no comparison to report on. Its category is still
    # BL_COMPARISON; there is simply no document verdict, so it keeps the
    # default OK/no-defect body rather than being flagged for review.
    if not escalate_stage.expects_comparison(email):
        report.evidence = "No documents attached and none expected — nothing to compare."
        return ProcessedEmail(report, attachment_count=attachment_count)

    attachments = list(email.get("attachments") or [])
    si_path, bl_path = escalate_stage.classify_attachments(attachments)

    si_text: str | None = None
    bl_text: str | None = None
    si_fields: dict[str, str] = {}
    bl_fields: dict[str, str] = {}
    si_labels: dict[str, str] = {}
    bl_labels: dict[str, str] = {}
    si_error = bl_error = ""

    if si_path:
        si_text, si_fields, si_labels, si_error = _read(source, si_path)
    if bl_path:
        bl_text, bl_fields, bl_labels, bl_error = _read(source, bl_path)

    bl_is_bl = bool(bl_text) and escalate_stage.looks_like_bill_of_lading(
        bl_text, bl_fields
    )

    reason = escalate_stage.check_escalation(
        attachments=attachments,
        si_readable=si_path is not None and si_text is not None,
        bl_readable=bl_path is not None and bl_text is not None,
        bl_is_bill_of_lading=bl_is_bl,
        si_fields=si_fields,
        bl_fields=bl_fields,
    )

    comparison = compare_stage.compare_fields(si_fields, bl_fields)
    for item in comparison:
        item.si_label = si_labels.get(item.field)
        item.bl_label = bl_labels.get(item.field)
    compare_stage.annotate(comparison)
    report.fields = comparison

    defects = compare_stage.defect_fields(comparison) if reason is None else []

    if reason is not None:
        result.status = Status.NEEDS_REVIEW
        result.review_reason = reason
        result.has_defect = False
        result.defect_fields = []
    elif defects:
        result.status = Status.MISMATCH
        result.has_defect = True
        result.defect_fields = defects
    else:
        result.status = Status.OK
        result.has_defect = False
        result.defect_fields = []

    report.evidence = _build_evidence(
        reason, defects, attachments, bl_text, si_error, bl_error,
        si_fields, bl_fields,
    )
    return ProcessedEmail(
        report,
        _excerpt(si_text),
        _excerpt(bl_text),
        attachment_count=attachment_count,
    )


def load_inbox(source: Path = DEFAULT_SOURCE):
    """The dataset bundle's own Inbox, for a local folder or a server URL."""
    sys.path.insert(0, str(source))
    from loader import Inbox  # ships with the dataset bundle

    return Inbox(str(source))


def process_inbox(source: Path = DEFAULT_SOURCE) -> dict[str, ProcessedEmail]:
    """Run every email through the pipeline, keyed by email_id.

    This is the expensive call — it reads ~250 attachments and may consult
    Gemini for the ambiguous ~4%. Callers that serve web requests must cache
    the result rather than invoking it per page load.
    """
    return {
        email["email_id"]: process_email(email, source) for email in load_inbox(source)
    }


def build_submission(source: Path = DEFAULT_SOURCE) -> dict[str, dict]:
    """Process the whole inbox into the submission shape."""
    return {
        email_id: processed.result.to_submission()
        for email_id, processed in process_inbox(source).items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--out", default=str(REPO_ROOT / "submission.json"))
    args = parser.parse_args(argv)

    submission = build_submission(Path(args.source))
    Path(args.out).write_text(json.dumps(submission, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for entry in submission.values():
        key = f"{entry['category']}/{entry['status']}"
        counts[key] = counts.get(key, 0) + 1
    print(f"wrote {len(submission)} entries to {args.out}")
    for key in sorted(counts):
        print(f"  {key:<32} {counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
