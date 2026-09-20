"""Stage 3: deterministic field-by-field diff between SI and BL.

status is OK (all 7 match) or MISMATCH (>=1 differs) *only once both
documents were read successfully* — a missing/unreadable field routes to
escalate.py's NEEDS_REVIEW instead of being silently treated as a mismatch
(see the dataset's status/has_defect table in data README).

No LLM here by design: once the fields are extracted the comparison is a
pure function, and a deterministic diff is reproducible and auditable in a
way a model call is not.

Normalization exists to stop *formatting* differences from being reported as
defects. The real pairs write the same weight as "243588" and "243,588", and
the same party in upper and mixed case, because SI and BL are produced by
different systems. Those are not defects. What normalization deliberately
does NOT do is strip parenthetical port codes or reorder words: in this
dataset "MOMBASA, KENYA (KEMBA)" vs "TUTICORIN, INDIA (KEMBA)" is a genuine
seeded defect where the code was left stale, and over-normalizing would hide
exactly the thing the pipeline exists to catch.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.pipeline.extract import is_usable
from app.pipeline.models import COMPARISON_FIELDS, FieldValue

# A comma between two digits is a thousands separator; a comma anywhere else
# (e.g. "MOMBASA, KENYA") is part of the text and must survive.
_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d)")


def normalize_value(value: str) -> str:
    """Reduce a raw field value to its comparable form.

    Whitespace collapsed and trimmed, thousands separators removed from
    numbers, then case-folded. Everything else is left alone.
    """
    collapsed = re.sub(r"\s+", " ", value).strip()
    without_separators = _THOUSANDS_SEPARATOR.sub("", collapsed)
    return without_separators.casefold()


def values_match(si_value: str, bl_value: str) -> bool:
    """Do these two raw values mean the same thing?"""
    return normalize_value(si_value) == normalize_value(bl_value)


def compare_fields(si_fields: dict, bl_fields: dict) -> list[FieldValue]:
    """Diff the 7 comparison fields.

    Returns one FieldValue per field, always in COMPARISON_FIELDS order.
    `match` is tri-state and mirrors the extraction contract:

        True   both sides have a usable value and they agree
        False  both sides have a usable value and they differ  -> a defect
        None   at least one side is missing or blank, so no verdict is
               possible — stage 4 decides what kind of review that needs

    A None never becomes a defect. That is the rule the dataset README is
    explicit about: an unreadable or blank field is NEEDS_REVIEW, never
    MISMATCH.
    """
    results: list[FieldValue] = []
    for name in COMPARISON_FIELDS:
        si_value = si_fields.get(name)
        bl_value = bl_fields.get(name)

        if is_usable(si_fields, name) and is_usable(bl_fields, name):
            match = values_match(si_value, bl_value)
        else:
            match = None

        results.append(
            FieldValue(field=name, si_value=si_value, bl_value=bl_value, match=match)
        )
    return results


def defect_fields(comparison: list[FieldValue]) -> list[str]:
    """Field names that were compared and genuinely differ."""
    return [item.field for item in comparison if item.match is False]


def uncomparable_fields(comparison: list[FieldValue]) -> list[str]:
    """Field names that could not be compared at all."""
    return [item.field for item in comparison if item.match is None]


def all_fields_comparable(comparison: list[FieldValue]) -> bool:
    return not uncomparable_fields(comparison)


# --- display-only annotation ---------------------------------------------
# Everything below describes a verdict that compare_fields() has already
# decided. It never changes `match`, so it cannot change defect_fields, the
# status, or a single byte of submission.json.

# Two values this similar, yet still different, are more likely a typo or a
# punctuation slip than two genuinely different parties. Deliberately high:
# the point is to catch "PTE LTD" vs "PTE. LTD.", not to excuse real
# differences. "MOMBASA, KENYA (KEMBA)" vs "TUTICORIN, INDIA (KEMBA)" scores
# well below it and is correctly left as a plain defect.
NEAR_MATCH_RATIO = 0.90


def similarity(si_value: str, bl_value: str) -> float:
    """How alike two values are once normalized, in 0..1."""
    return SequenceMatcher(
        None, normalize_value(si_value), normalize_value(bl_value)
    ).ratio()


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _is_near_miss(si_value: str, bl_value: str) -> bool:
    """Is this difference small enough to look like a typo rather than a defect?

    Character similarity alone is not enough, because it is blind to what
    changed. "10 x 40'HC" and "11 x 40'HC" differ by a single character and
    score 0.95, but one container is a real, serious discrepancy — exactly
    what this pipeline exists to catch. So any difference in the digits
    disqualifies a pair outright, and only a punctuation, spacing or casing
    difference ("ACME PTE LTD" vs "ACME PTE. LTD.") can be a near miss.
    """
    if _digits(si_value) != _digits(bl_value):
        return False
    return similarity(si_value, bl_value) >= NEAR_MATCH_RATIO


def describe(item: FieldValue) -> str | None:
    """A caveat worth showing next to this field's verdict, if any.

    Two cases are worth a reviewer's attention even though the verdict is
    settled:

    - a match that only held *because* of normalization, so the documents
      do literally disagree on the page even though they mean the same
      thing;
    - a difference small enough to look like a typo, which a human should
      confirm is a real defect rather than a slip.
    """
    if item.match is True and item.si_value != item.bl_value:
        return "matches only after normalizing formatting"

    if item.match is False and _is_near_miss(item.si_value, item.bl_value):
        return "near miss — differs only in punctuation or spacing"

    return None


def annotate(comparison: list[FieldValue]) -> list[FieldValue]:
    """Attach display-only notes to each compared field. Mutates in place."""
    for item in comparison:
        item.note = describe(item)
    return comparison
