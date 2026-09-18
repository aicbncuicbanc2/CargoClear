"""Stage 2 tests.

The email_004 fixtures below reproduce the label/value pairs recorded in
docs/manual-trace-email_004.md — the one SI/BL pair traced by hand against
the real dataset. They are the regression anchor for alias matching: the SI
and BL deliberately use different labels for the same four fields.
"""

from __future__ import annotations

import pytest

from app.pipeline.extract import (
    FIELD_ALIASES,
    extract_fields,
    is_blank_value,
    normalize_label,
)
from app.pipeline.models import COMPARISON_FIELDS

EMAIL_004_SI = """SHIPPING INSTRUCTION
Booking Ref: PO 26067

Shipper: APRIL FAR EAST (M) SDN BHD
Consignee (Non-Negotiable): EAST BRIGHT FZ-LLC
Notify: EAST BRIGHT FZ-LLC
Port of Loading (POL): NANTONG, CHINA (CNNTG)
POD: KARACHI, PAKISTAN (PKKHI)
Total Containers: 6 x 40'HC
Gross Wt (kgs): 131,058 KG
Commodity: COATED IVORY BOARD
"""

EMAIL_004_BL = """BILL OF LADING (DRAFT)
B/L No: SIN2609887

SHIPPER: APRIL FAR EAST (M) SDN BHD
To the Order of: UAB NOVAKOPA
Notify Party: UAB NOVAKOPA
Port of Loading (POL): NANTONG, CHINA (CNNTG)
POD: KARACHI, PAKISTAN (PKKHI)
Container Count: 6 x 40'HC
Gross Weight (KG): 131,058 KG
"""


def test_si_extracts_all_seven_fields():
    fields = extract_fields(EMAIL_004_SI)
    assert fields == {
        "shipper": "APRIL FAR EAST (M) SDN BHD",
        "consignee": "EAST BRIGHT FZ-LLC",
        "notify_party": "EAST BRIGHT FZ-LLC",
        "port_of_loading": "NANTONG, CHINA (CNNTG)",
        "port_of_discharge": "KARACHI, PAKISTAN (PKKHI)",
        "container_count": "6 x 40'HC",
        "gross_weight_kg": "131,058 KG",
    }


def test_bl_extracts_all_seven_fields_despite_different_labels():
    fields = extract_fields(EMAIL_004_BL)
    assert fields == {
        "shipper": "APRIL FAR EAST (M) SDN BHD",
        "consignee": "UAB NOVAKOPA",
        "notify_party": "UAB NOVAKOPA",
        "port_of_loading": "NANTONG, CHINA (CNNTG)",
        "port_of_discharge": "KARACHI, PAKISTAN (PKKHI)",
        "container_count": "6 x 40'HC",
        "gross_weight_kg": "131,058 KG",
    }


def test_traced_defect_fields_are_the_two_that_differ():
    """The trace's ground truth: consignee + notify_party differ, rest match."""
    si = extract_fields(EMAIL_004_SI)
    bl = extract_fields(EMAIL_004_BL)
    differing = sorted(f for f in COMPARISON_FIELDS if si[f] != bl[f])
    assert differing == ["consignee", "notify_party"]


def test_every_field_key_is_always_present():
    fields = extract_fields("Subject: nothing useful here")
    assert set(fields) == set(COMPARISON_FIELDS)
    assert all(value is None for value in fields.values())


def test_block_layout_value_on_following_lines():
    text = """Shipper:
ACME EXPORTS SDN BHD
LOT 5, JALAN PERUSAHAAN

Consignee: NORTHWIND TRADING GMBH
"""
    fields = extract_fields(text)
    assert fields["shipper"] == "ACME EXPORTS SDN BHD LOT 5, JALAN PERUSAHAAN"
    assert fields["consignee"] == "NORTHWIND TRADING GMBH"


def test_blank_markers_read_as_missing_not_as_values():
    text = """Shipper: APRIL FAR EAST (M) SDN BHD
Consignee: ???
Notify Party: ______
Port of Loading: TBA
POD: N/A
Container Count: 6 x 40'HC
Gross Weight (KG):
"""
    fields = extract_fields(text)
    assert fields["shipper"] == "APRIL FAR EAST (M) SDN BHD"
    for field in [
        "consignee",
        "notify_party",
        "port_of_loading",
        "port_of_discharge",
        "gross_weight_kg",
    ]:
        assert fields[field] is None, field


@pytest.mark.parametrize(
    "value",
    ["", "   ", "???", "______", "TBA", "n/a", "-", "To Be Advised", "....."],
)
def test_is_blank_value_recognizes_write_in_blanks(value):
    assert is_blank_value(value)


def test_is_blank_value_accepts_real_values():
    assert not is_blank_value("UAB NOVAKOPA")
    assert not is_blank_value("6 x 40'HC")


def test_tab_and_column_separated_labels():
    text = "Shipper\tAPRIL FAR EAST (M) SDN BHD\nPOD     KARACHI, PAKISTAN (PKKHI)\n"
    fields = extract_fields(text)
    assert fields["shipper"] == "APRIL FAR EAST (M) SDN BHD"
    assert fields["port_of_discharge"] == "KARACHI, PAKISTAN (PKKHI)"


def test_better_ranked_alias_wins_over_earlier_weaker_one():
    """A BL listing both Place of Receipt and Port of Loading must report
    the actual load port, not the receipt place, whatever the page order."""
    text = """Place of Receipt: SHAH ALAM, MALAYSIA
Port of Loading: PORT KLANG, MALAYSIA
Place of Delivery: HAMBURG INLAND DEPOT
Port of Discharge: ROTTERDAM, NETHERLANDS
"""
    fields = extract_fields(text)
    assert fields["port_of_loading"] == "PORT KLANG, MALAYSIA"
    assert fields["port_of_discharge"] == "ROTTERDAM, NETHERLANDS"


def test_first_occurrence_wins_for_repeated_equal_rank_labels():
    text = "Shipper: FIRST VALUE SDN BHD\nShipper: FOOTER REPEAT BHD\n"
    assert extract_fields(text)["shipper"] == "FIRST VALUE SDN BHD"


def test_short_aliases_do_not_fire_inside_unrelated_labels():
    """'POD' must not be matched by 'Method of Transport' etc. Matching is
    whole-label, not substring."""
    text = "Freight Payable At: SINGAPORE\nPre-carriage by: TRUCK\n"
    fields = extract_fields(text)
    assert fields["port_of_discharge"] is None
    assert fields["port_of_loading"] is None


def test_normalize_label_flattens_punctuation_and_case():
    assert normalize_label("Gross Wt (kgs)") == "gross wt kgs"
    assert normalize_label("Consignee (Non-Negotiable)") == "consignee non negotiable"
    assert normalize_label("  NOTIFY  PARTY  ") == "notify party"


def test_alias_table_covers_exactly_the_seven_fields():
    assert set(FIELD_ALIASES) == set(COMPARISON_FIELDS)
