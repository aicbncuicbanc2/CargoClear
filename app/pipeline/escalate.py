"""Stage 4: decide whether an email/comparison needs human review.

review_reason values (exact, per data README) and their triggers:

    wrong_doc_type      the 2nd attachment isn't actually a BL (e.g. a
                         Commercial Invoice / Packing List / Certificate
                         of Origin was attached instead)
    missing_attachment  0 attachments, or only the SI with no BL
    unreadable          image-only scanned PDF (no text layer), empty
                         0-byte file, or truncated/garbled PDF
    missing_value       a required field is blank (???, ______, TBA) in
                         an otherwise-complete document

A blank/unreadable field is NOT a mismatch — status is NEEDS_REVIEW with
has_defect=False, never MISMATCH. 20 of the 520 emails (email_501-520) are
edge cases purpose-built to test this, 5 per review_reason.

Placeholder for now — filled in Sun 20 Sep per the build plan.
"""

from app.pipeline.models import ReviewReason


def check_escalation(*args, **kwargs) -> ReviewReason | None:
    raise NotImplementedError("check_escalation: to be built Sun 20 Sep")
