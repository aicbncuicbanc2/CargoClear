"""Tests for the display-only explainability layer.

Everything exercised here annotates a verdict that has already been decided.
The load-bearing assertion is test_annotation_never_changes_the_verdict: none
of it may alter defect_fields, and therefore none of it may alter
submission.json.
"""

from __future__ import annotations

import pytest

from app.pipeline.classify import matched_signals
from app.pipeline.compare import (
    annotate,
    compare_fields,
    defect_fields,
    describe,
    similarity,
)
from app.pipeline.extract import extract_fields, extract_with_labels, match_label_detail
from app.pipeline.models import Category, FieldValue


# --- labels ---------------------------------------------------------------


def test_labels_record_each_document_own_wording():
    """The whole point: same field, different header in each document."""
    si_fields, si_labels = extract_with_labels("Port of Loading: SINGAPORE\n")
    bl_fields, bl_labels = extract_with_labels("Load Port: SINGAPORE\n")

    assert si_fields["port_of_loading"] == bl_fields["port_of_loading"] == "SINGAPORE"
    assert si_labels["port_of_loading"] == "Port of Loading"
    assert bl_labels["port_of_loading"] == "Load Port"


def test_labels_are_not_left_with_a_dangling_bracket():
    """The alias pattern consumes the closing bracket; the label must not
    then read "Load Port (POL"."""
    _fields, labels = extract_with_labels("Load Port (POL): SINGAPORE\n")
    assert labels["port_of_loading"] == "Load Port"


def test_extract_fields_is_unchanged_by_the_label_refactor():
    text = "Shipper: ACME\nConsignee:\nBETA LTD\nGross Wt (kgs): 243,588\n"
    assert extract_fields(text) == extract_with_labels(text)[0]


def test_match_label_detail_reports_the_label_and_match_label_still_does_not():
    detail = match_label_detail("Notify Party: SOMEONE")
    assert detail == ("notify_party", detail[1], "SOMEONE", "Notify Party")


def test_labels_only_cover_fields_that_were_found():
    _fields, labels = extract_with_labels("Shipper: ACME\n")
    assert set(labels) == {"shipper"}


# --- classifier signals ---------------------------------------------------


def test_signals_report_what_the_classifier_keyed_on():
    email = {
        "email_id": "email_001",
        "subject": "Please check the draft BL against the SI",
        "body": "kindly verify",
        "attachments": ["a_SI.txt", "b_BL.txt"],
    }
    signals = matched_signals(email, Category.BL_COMPARISON)

    assert any("draft BL" in signal for signal in signals)
    assert "carries both an SI and a BL attachment" in signals


def test_signals_are_ordered_by_weight():
    """A reader wants the deciding signal first, not a transcript."""
    email = {
        "subject": "draft BL",  # heavy subject signal
        "body": "please verify",  # light body signal
        "attachments": [],
    }
    signals = matched_signals(email, Category.BL_COMPARISON)
    assert "subject" in signals[0]


def test_no_signals_when_nothing_matches():
    assert matched_signals({"subject": "lunch?", "body": ""}, Category.SPAM) == []


# --- borderline annotation ------------------------------------------------


def test_match_that_only_survived_normalization_is_flagged():
    item = FieldValue(
        field="gross_weight_kg", si_value="243588", bl_value="243,588", match=True
    )
    assert describe(item) == "matches only after normalizing formatting"


def test_identical_values_get_no_note():
    item = FieldValue(field="shipper", si_value="ACME", bl_value="ACME", match=True)
    assert describe(item) is None


def test_punctuation_only_difference_is_a_near_miss():
    item = FieldValue(
        field="shipper",
        si_value="ACME PTE LTD",
        bl_value="ACME PTE. LTD.",
        match=False,
    )
    assert describe(item) == "near miss — differs only in punctuation or spacing"


def test_a_digit_difference_is_never_a_near_miss():
    """One container is a real discrepancy, however few characters it moves.

    These two strings are >0.9 similar, so a naive similarity threshold would
    soften exactly the defect this pipeline exists to catch.
    """
    item = FieldValue(
        field="container_count",
        si_value="10 x 40'HC",
        bl_value="11 x 40'HC",
        match=False,
    )
    assert similarity(item.si_value, item.bl_value) >= 0.9
    assert describe(item) is None


def test_a_genuinely_different_port_is_not_a_near_miss():
    item = FieldValue(
        field="port_of_discharge",
        si_value="MOMBASA, KENYA (KEMBA)",
        bl_value="TUTICORIN, INDIA (KEMBA)",
        match=False,
    )
    assert describe(item) is None


def test_uncomparable_fields_get_no_note():
    item = FieldValue(field="shipper", si_value="ACME", bl_value=None, match=None)
    assert describe(item) is None


def test_annotation_never_changes_the_verdict():
    """The guard that keeps submission.json stable."""
    si = {
        "shipper": "ACME PTE LTD",
        "consignee": "BETA",
        "port_of_loading": "MOMBASA, KENYA (KEMBA)",
        "gross_weight_kg": "243588",
    }
    bl = {
        "shipper": "ACME PTE. LTD.",
        "consignee": "BETA",
        "port_of_loading": "TUTICORIN, INDIA (KEMBA)",
        "gross_weight_kg": "243,588",
    }
    comparison = compare_fields(si, bl)
    before = defect_fields(comparison)
    matches_before = [item.match for item in comparison]

    annotate(comparison)

    assert defect_fields(comparison) == before
    assert [item.match for item in comparison] == matches_before
    # ...and the near miss is still counted as a defect, merely annotated.
    assert "shipper" in before
