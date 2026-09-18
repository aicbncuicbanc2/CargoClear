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

The reasons are checked in the order above minus wrong_doc_type, which needs
readable text first; the real precedence is:

    missing_attachment -> unreadable -> wrong_doc_type -> missing_value

which is simply the order in which each step becomes possible. You cannot
judge a document's type before you can read it, and you cannot judge its
values before you know it is the right kind of document.
"""

from __future__ import annotations

import re

from app.pipeline.extract import blank_fields
from app.pipeline.models import COMPARISON_FIELDS, ReviewReason

# Document titles that positively identify a non-BL. Observed in the
# wrong_doc_type group: Commercial Invoice (501), Packing List (502, 504),
# Certificate of Origin (503, 505).
NON_BL_TITLES = (
    "commercial invoice",
    "proforma invoice",
    "packing list",
    "certificate of origin",
    "delivery order",
    "debit note",
    "credit note",
    "cargo manifest",
)

# "bill of lading instruction" is an SI heading, not a BL — 10 of the SI
# documents use it, so the BL marker has to exclude it explicitly.
_BL_TITLE = re.compile(r"bill\s+of\s+lading(?!\s+instruction)", re.IGNORECASE)
_BL_NUMBER = re.compile(r"\bb\s*/?\s*l\s*(?:no|number|#)", re.IGNORECASE)

# How much of a document to consider its "header" when looking for a title.
HEADER_LINES = 15

# A BL that carries fewer than this many of the 7 fields is not BL-shaped,
# whatever its header says. Kept low: the point is to catch a document of a
# different kind, not to penalise a BL with a couple of blank boxes.
MIN_BL_FIELDS = 3


def looks_like_bill_of_lading(text: str, fields: dict[str, str] | None = None) -> bool:
    """Does this document look like a Bill of Lading at all?

    Two independent signals, because neither alone is safe. The title is the
    strongest evidence — every genuine BL in this dataset says "BILL OF
    LADING" in its first couple of lines, and each wrong_doc_type file
    announces itself as something else. But a Packing List also carries
    Shipper and Consignee, so structure alone would pass it; and a BL whose
    header the reader mangled would fail a title-only check. So: an explicit
    foreign title is disqualifying, an explicit BL marker is qualifying, and
    otherwise fall back to whether the document is BL-shaped.
    """
    header = "\n".join(
        line for line in text.splitlines() if line.strip()
    ).splitlines()[:HEADER_LINES]
    header_text = "\n".join(header)

    if any(title in header_text.lower() for title in NON_BL_TITLES):
        return False
    if _BL_TITLE.search(header_text) or _BL_NUMBER.search(header_text):
        return True

    # No title either way — judge by shape.
    if fields is None:
        return False
    return sum(1 for name in COMPARISON_FIELDS if name in fields) >= MIN_BL_FIELDS


# Phrases that mean documents were meant to be here. Deliberately specific:
# 94 BL_COMPARISON emails carry a security banner reading "please exercise
# caution with attachments", so a bare match on "attach" would read every
# one of them as claiming an attachment it does not have.
_EXPECTS_COMPARISON = re.compile(
    r"\bcompare\b"
    r"|\battached\s+(?:are|is|herewith|please)\b"
    r"|\bplease\s+find\s+attached\b"
    r"|\battachments?\s+(?:appear|have|was|were)\b"
    r"|\benclosed\b"
    r"|\bstill\s+missing\b",
    re.IGNORECASE,
)


def expects_comparison(email: dict) -> bool:
    """Was this email meant to carry documents to compare?

    A BL_COMPARISON email is not automatically a comparison *task*. 91 of
    them in this inbox read "Please assist to send the draft BL ... for
    checking" — they are asking for a draft to be produced, and nothing was
    ever attached or expected. Calling those missing_attachment would flag
    96 emails for review where the dataset intends 5.

    The ones that genuinely are failed comparisons say so: "Please compare
    the SI and draft BL ... (attachments appear to have been dropped)".
    """
    if email.get("attachments"):
        return True
    haystack = f"{email.get('subject', '')}\n{email.get('body', '')}"
    return bool(_EXPECTS_COMPARISON.search(haystack))


def classify_attachments(attachments: list[str]) -> tuple[str | None, str | None]:
    """Split an email's attachments into (SI path, BL path).

    The bundle names them "..._SI.ext" / "..._BL.ext". Falls back to
    positional order so the pipeline still works on a differently named
    inbox: first attachment is the SI, second is the document to check.
    """
    si = next((path for path in attachments if "_SI." in path.upper()), None)
    bl = next((path for path in attachments if "_BL." in path.upper()), None)

    if si is None and bl is None:
        if len(attachments) >= 2:
            return attachments[0], attachments[1]
        if len(attachments) == 1:
            return attachments[0], None
    return si, bl


def check_escalation(
    *,
    attachments: list[str],
    si_readable: bool = True,
    bl_readable: bool = True,
    bl_is_bill_of_lading: bool = True,
    si_fields: dict[str, str] | None = None,
    bl_fields: dict[str, str] | None = None,
) -> ReviewReason | None:
    """Return the review reason for a BL_COMPARISON email, or None if the
    comparison can be trusted.

    Keyword-only: the caller passes facts already established by the earlier
    stages rather than this function re-reading anything, so the decision is
    testable in isolation and the ordering above stays explicit.
    """
    si_path, bl_path = classify_attachments(attachments)

    # 1. Nothing to compare against.
    if not attachments or si_path is None or bl_path is None:
        return ReviewReason.MISSING_ATTACHMENT

    # 2. Something is there but cannot be read.
    if not si_readable or not bl_readable:
        return ReviewReason.UNREADABLE

    # 3. Readable, but the second document is not a BL.
    if not bl_is_bill_of_lading:
        return ReviewReason.WRONG_DOC_TYPE

    # 4. Right documents, but a field was left blank. Checked after doc type
    #    so a Commercial Invoice's absent fields never surface as blanks.
    si_fields = si_fields or {}
    bl_fields = bl_fields or {}
    if blank_fields(si_fields) or blank_fields(bl_fields):
        return ReviewReason.MISSING_VALUE

    # A field neither side mentions at all is also uncomparable. It is not a
    # blank box on a form, so missing_value is the closest honest reason:
    # the value needed to decide is missing.
    for name in COMPARISON_FIELDS:
        if not si_fields.get(name) or not bl_fields.get(name):
            return ReviewReason.MISSING_VALUE

    return None
