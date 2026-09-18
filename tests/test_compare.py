"""Stage 3 tests."""

from __future__ import annotations

import pytest

from app.pipeline.compare import (
    all_fields_comparable,
    compare_fields,
    defect_fields,
    normalize_value,
    uncomparable_fields,
    values_match,
)
from app.pipeline.models import COMPARISON_FIELDS

COMPLETE = {
    "shipper": "APRIL FAR EAST (M) SDN BHD",
    "consignee": "EAST BRIGHT FZ-LLC",
    "notify_party": "EAST BRIGHT FZ-LLC",
    "port_of_loading": "NANTONG, CHINA (CNNTG)",
    "port_of_discharge": "KARACHI, PAKISTAN (PKKHI)",
    "container_count": "6 x 40'HC",
    "gross_weight_kg": "131,058 KG",
}


def test_identical_documents_produce_no_defects():
    comparison = compare_fields(COMPLETE, dict(COMPLETE))
    assert defect_fields(comparison) == []
    assert all_fields_comparable(comparison)
    assert all(item.match is True for item in comparison)


def test_thousands_separator_is_not_a_defect():
    """Observed in 5 real pairs: the xlsx SI writes 243588, the docx BL
    writes 243,588. Same weight, different system formatting it."""
    assert values_match("243588", "243,588")
    comparison = compare_fields(
        {**COMPLETE, "gross_weight_kg": "243588"},
        {**COMPLETE, "gross_weight_kg": "243,588"},
    )
    assert defect_fields(comparison) == []


def test_case_and_whitespace_are_not_defects():
    assert values_match("east bright fz-llc", "EAST BRIGHT FZ-LLC")
    assert values_match("  PORT  KLANG,  MALAYSIA ", "PORT KLANG, MALAYSIA")


def test_real_defect_is_still_reported():
    comparison = compare_fields(
        COMPLETE, {**COMPLETE, "consignee": "UAB NOVAKOPA"}
    )
    assert defect_fields(comparison) == ["consignee"]


def test_normalization_does_not_erase_a_stale_port_code_defect():
    """email_013 keeps the SI's port code on a different port. Stripping
    parentheticals would hide exactly the defect we exist to catch."""
    assert not values_match("MOMBASA, KENYA (KEMBA)", "TUTICORIN, INDIA (KEMBA)")


def test_comma_outside_a_number_survives_normalization():
    assert normalize_value("MOMBASA, KENYA") == "mombasa, kenya"
    assert normalize_value("243,588 KG") == "243588 kg"


def test_blank_on_either_side_is_never_a_defect():
    """The dataset README is explicit: a blank field is NEEDS_REVIEW, never
    MISMATCH."""
    comparison = compare_fields(COMPLETE, {**COMPLETE, "consignee": ""})
    consignee = next(i for i in comparison if i.field == "consignee")
    assert consignee.match is None
    assert defect_fields(comparison) == []
    assert uncomparable_fields(comparison) == ["consignee"]


def test_absent_on_either_side_is_never_a_defect():
    partial = {k: v for k, v in COMPLETE.items() if k != "notify_party"}
    comparison = compare_fields(COMPLETE, partial)
    assert defect_fields(comparison) == []
    assert uncomparable_fields(comparison) == ["notify_party"]


def test_every_field_is_reported_in_canonical_order():
    comparison = compare_fields({}, {})
    assert [item.field for item in comparison] == COMPARISON_FIELDS
    assert all(item.match is None for item in comparison)
    assert defect_fields(comparison) == []


@pytest.mark.parametrize(
    ("si", "bl", "expected"),
    [
        ("6 x 40'HC", "6 x 40'HC", True),
        ("6 x 40'HC", "5 x 40'HC", False),
        ("131,058 KG", "131058 KG", True),
        ("131,058 KG", "131,058 kg", True),
        ("1,234,567", "1234567", True),
    ],
)
def test_value_matching_cases(si, bl, expected):
    assert values_match(si, bl) is expected
