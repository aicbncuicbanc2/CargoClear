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
from pathlib import Path

from app.pipeline import compare as compare_stage
from app.pipeline import escalate as escalate_stage
from app.pipeline.classify import classify_email
from app.pipeline.extract import UnreadableDocument, extract_fields, read_document
from app.pipeline.models import (
    Category,
    EmailReport,
    EmailResult,
    ReviewReason,
    Status,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SOURCE = REPO_ROOT / "data"


def _read(source: Path, attachment: str) -> tuple[str | None, dict[str, str]]:
    """Read one attachment. Returns (text, fields); text is None if the
    document could not be read at all."""
    try:
        text = read_document(Path(source) / attachment)
    except UnreadableDocument:
        return None, {}
    return text, extract_fields(text)


def process_email(email: dict, source: Path = DEFAULT_SOURCE) -> EmailReport:
    """Run one email through all four stages."""
    email_id = email.get("email_id", "")
    category, _confidence = classify_email(email)

    result = EmailResult(category=category)
    report = EmailReport(
        email_id=email_id,
        subject=email.get("subject", ""),
        sender=email.get("from") or email.get("sender", ""),
        result=result,
    )

    if category is not Category.BL_COMPARISON:
        return report

    # A BL_COMPARISON email that never carried documents and never asked for
    # a comparison (91 of them read "please assist to send the draft BL for
    # checking") has no comparison to report on. Its category is still
    # BL_COMPARISON; there is simply no document verdict, so it keeps the
    # default OK/no-defect body rather than being flagged for review.
    if not escalate_stage.expects_comparison(email):
        report.evidence = "No documents attached and none expected — nothing to compare."
        return report

    attachments = list(email.get("attachments") or [])
    si_path, bl_path = escalate_stage.classify_attachments(attachments)

    si_text: str | None = None
    bl_text: str | None = None
    si_fields: dict[str, str] = {}
    bl_fields: dict[str, str] = {}

    if si_path:
        si_text, si_fields = _read(source, si_path)
    if bl_path:
        bl_text, bl_fields = _read(source, bl_path)

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
    report.fields = comparison

    if reason is not None:
        result.status = Status.NEEDS_REVIEW
        result.review_reason = reason
        result.has_defect = False
        result.defect_fields = []
        return report

    defects = compare_stage.defect_fields(comparison)
    if defects:
        result.status = Status.MISMATCH
        result.has_defect = True
        result.defect_fields = defects
    else:
        result.status = Status.OK
        result.has_defect = False
        result.defect_fields = []
    return report


def build_submission(source: Path = DEFAULT_SOURCE) -> dict[str, dict]:
    """Process the whole inbox into the submission shape."""
    sys.path.insert(0, str(source))
    from loader import Inbox  # ships with the dataset bundle

    inbox = Inbox(str(source))
    return {
        email["email_id"]: process_email(email, source).result.to_submission()
        for email in inbox
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
