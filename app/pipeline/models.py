"""Shared data shapes for the pipeline.

These match the dataset's actual required output shape exactly (see
sample_submission.json / data README), not just the general problem
statement wording — the enum values below are what /submit scoring expects.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Category(str, Enum):
    BL_COMPARISON = "BL_COMPARISON"
    SI_REQUEST = "SI_REQUEST"
    INVOICE_QUERY = "INVOICE_QUERY"
    GENERAL = "GENERAL"
    SPAM = "SPAM"


class Status(str, Enum):
    OK = "OK"  # compared cleanly, all 7 fields match
    MISMATCH = "MISMATCH"  # compared cleanly, >=1 field differs
    NEEDS_REVIEW = "NEEDS_REVIEW"  # could not be compared confidently


class ReviewReason(str, Enum):
    WRONG_DOC_TYPE = "wrong_doc_type"  # 2nd attachment isn't actually a BL
    MISSING_ATTACHMENT = "missing_attachment"  # no BL (or no attachments) to compare
    UNREADABLE = "unreadable"  # scanned image / empty / garbled file
    MISSING_VALUE = "missing_value"  # a required field is blank (???, TBA, etc.)


# The 7 fields checked between SI and BL, per the problem statement.
COMPARISON_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]


class EmailResult(BaseModel):
    """One entry of the submission dict, keyed by email_id.

    Mirrors data/sample_submission.json exactly:
        {"category": "BL_COMPARISON", "status": "MISMATCH",
         "review_reason": null, "has_defect": true,
         "defect_fields": ["consignee"]}
    """

    category: Category
    status: Status = Status.OK
    review_reason: Optional[ReviewReason] = None
    has_defect: bool = False
    defect_fields: list[str] = []

    def to_submission(self) -> dict:
        return {
            "category": self.category.value,
            "status": self.status.value,
            "review_reason": self.review_reason.value if self.review_reason else None,
            "has_defect": self.has_defect,
            "defect_fields": self.defect_fields,
        }


# --- extra shapes used internally by the UI / pipeline, not part of the
# submission format itself ---


class FieldValue(BaseModel):
    field: str
    si_value: Optional[str] = None
    bl_value: Optional[str] = None
    match: Optional[bool] = None  # None when a value is missing/unreadable


class EmailReport(BaseModel):
    """What the UI renders for one email: the submission verdict plus the
    evidence (per-field SI/BL values) behind it."""

    email_id: str
    subject: str
    sender: str
    result: EmailResult
    fields: list[FieldValue] = []
    evidence: Optional[str] = None
