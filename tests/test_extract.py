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
    blank_fields,
    extract_fields,
    is_blank,
    is_blank_value,
    is_present,
    is_usable,
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


def test_fields_never_mentioned_are_absent_not_blank():
    """Absent and blank must stay distinguishable: only blank is
    review_reason='missing_value'."""
    fields = extract_fields("Subject: nothing useful here")
    assert fields == {}
    for name in COMPARISON_FIELDS:
        assert not is_present(fields, name)
        assert not is_blank(fields, name)
        assert not is_usable(fields, name)


def test_block_layout_takes_the_first_line_below_the_label():
    """Only the identity line is taken, not the trailing address lines: SI
    and BL wrap the same party's address differently, so comparing whole
    blocks would manufacture mismatches."""
    text = """Shipper:
ACME EXPORTS SDN BHD
LOT 5, JALAN PERUSAHAAN

Consignee: NORTHWIND TRADING GMBH
"""
    fields = extract_fields(text)
    assert fields["shipper"] == "ACME EXPORTS SDN BHD"
    assert fields["consignee"] == "NORTHWIND TRADING GMBH"


def test_inline_value_ignores_following_address_lines():
    """The .pdf pairs write the name inline then continue the address."""
    text = """Shipper APRIL FINE PAPER TRADING
ON BEHALF OF VITAL SOLUTIONS PTE LTD
77 ROBINSON ROAD, #21-01
Load Port BUATAN, INDONESIA
"""
    fields = extract_fields(text)
    assert fields["shipper"] == "APRIL FINE PAPER TRADING"
    assert fields["port_of_loading"] == "BUATAN, INDONESIA"


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
    expected_blank = [
        "consignee",
        "notify_party",
        "port_of_loading",
        "port_of_discharge",
        "gross_weight_kg",
    ]
    for field in expected_blank:
        # Present in the document, but with no value: "" not absent.
        assert is_present(fields, field), field
        assert is_blank(fields, field), field
        assert fields[field] == "", field
    assert sorted(blank_fields(fields)) == sorted(expected_blank)


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
    assert not is_present(fields, "port_of_discharge")
    assert not is_present(fields, "port_of_loading")


def test_normalize_label_flattens_punctuation_and_case():
    assert normalize_label("Gross Wt (kgs)") == "gross wt kgs"
    assert normalize_label("Consignee (Non-Negotiable)") == "consignee non negotiable"
    assert normalize_label("  NOTIFY  PARTY  ") == "notify party"


def test_alias_table_covers_exactly_the_seven_fields():
    assert set(FIELD_ALIASES) == set(COMPARISON_FIELDS)


# --- regressions taken verbatim from data/attachments -----------------------
# Each line below was copied from a real document during the alias-extension
# pass; the bugs they pin were all found that way, not hypothesised.


def test_parenthesised_code_is_not_left_on_the_value():
    """'Port of Loading (POL): X' must not yield '): X'."""
    fields = extract_fields("Port of Loading (POL): PORT KLANG (WESTPORT), MALAYSIA (MYPKG)\n")
    assert fields["port_of_loading"] == "PORT KLANG (WESTPORT), MALAYSIA (MYPKG)"


def test_bilingual_gloss_label_from_xlsx_docx_pairs():
    """'Shipper (Principal or Seller) (发货人):' — the CJK gloss must not
    leak into the value."""
    text = (
        "Shipper (Principal or Seller) (发货人): APRIL FINE PAPER TRADING\n"
        "Consignee (收货人): AL GURG STATIONERY LLC\n"
        "装货港 Load Port: SINGAPORE\n"
    )
    fields = extract_fields(text)
    assert fields["shipper"] == "APRIL FINE PAPER TRADING"
    assert fields["consignee"] == "AL GURG STATIONERY LLC"


def test_inline_cjk_between_label_words():
    """'Gross Weight毛重(KGS):' appears in 55 lines across the .txt pairs."""
    fields = extract_fields("Gross Weight毛重(KGS): 67,311 KG\n")
    assert fields["gross_weight_kg"] == "67,311 KG"


def test_pdf_generator_newline_artifact_label():
    """8 of the 20 readable PDFs carry 'TOTAL Gross Weightnn(KGS):'."""
    fields = extract_fields("TOTAL Gross Weightnn(KGS): 23,702 KG\n")
    assert fields["gross_weight_kg"] == "23,702 KG"


def test_observed_real_aliases():
    text = """Shipper (Principal or Seller): ASIA PACIFIC PAPERBOARD TRADING PTE LTD
Notify Party/Intermediate Consignee: TOPKOPY MIDDLE EAST FZE
No. of Containers or Packages: 15 x 20'GP
Shipper/Exporter: IGNORED BECAUSE SHIPPER ALREADY SET
"""
    fields = extract_fields(text)
    assert fields["shipper"] == "ASIA PACIFIC PAPERBOARD TRADING PTE LTD"
    assert fields["notify_party"] == "TOPKOPY MIDDLE EAST FZE"
    assert fields["container_count"] == "15 x 20'GP"


def test_commercial_invoice_labels_do_not_populate_shipping_fields():
    """email_501_BL.txt is a Commercial Invoice standing in for a BL. Its
    'Seller:'/'Buyer:' lines must not be read as shipper/consignee, or
    wrong_doc_type becomes undetectable in stage 4."""
    text = """COMMERCIAL INVOICE
Invoice No.: 5250078266
Seller: APRIL FINE PAPER TRADING (MIDDLE EAST) FZE
Buyer: KPP-ANTALIS (SINGAPORE) PTE. LTD.
"""
    fields = extract_fields(text)
    assert fields == {}


def test_possessive_label_is_not_read_as_the_field():
    fields = extract_fields("Shipper's Reference: ABC-123\n")
    assert not is_present(fields, "shipper")


def test_net_weight_is_not_gross_weight():
    fields = extract_fields("Net Weight: 19,400 KG\n")
    assert not is_present(fields, "gross_weight_kg")
