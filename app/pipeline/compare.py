"""Stage 3: deterministic field-by-field diff between SI and BL.

status is OK (all 7 match) or MISMATCH (>=1 differs) *only once both
documents were read successfully* — a missing/unreadable field routes to
escalate.py's NEEDS_REVIEW instead of being silently treated as a mismatch
(see the dataset's status/has_defect table in data README).

Placeholder for now — filled in Sun 20 Sep per the build plan.
"""

from app.pipeline.models import FieldValue


def compare_fields(si_fields: dict, bl_fields: dict) -> list[FieldValue]:
    raise NotImplementedError("compare_fields: to be built Sun 20 Sep")
