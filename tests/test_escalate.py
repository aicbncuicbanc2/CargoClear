"""Stage 4 tests.

Fixtures are taken from the four purpose-built edge-case groups in the real
inbox (email_501-520), so these pin the actual triggers rather than
invented ones.
"""

from __future__ import annotations

from app.pipeline.escalate import (
    check_escalation,
    classify_attachments,
    expects_comparison,
    looks_like_bill_of_lading,
)
from app.pipeline.models import ReviewReason

PAIR = ["attachments/email_001_SI.txt", "attachments/email_001_BL.txt"]

COMPLETE = {
    "shipper": "APRIL FAR EAST (M) SDN BHD",
    "consignee": "EAST BRIGHT FZ-LLC",
    "notify_party": "EAST BRIGHT FZ-LLC",
    "port_of_loading": "NANTONG, CHINA (CNNTG)",
    "port_of_discharge": "KARACHI, PAKISTAN (PKKHI)",
    "container_count": "6 x 40'HC",
    "gross_weight_kg": "131,058 KG",
}


def test_complete_readable_pair_needs_no_review():
    assert (
        check_escalation(
            attachments=PAIR, si_fields=COMPLETE, bl_fields=dict(COMPLETE)
        )
        is None
    )


# --- missing_attachment (email_506-510) ------------------------------------


def test_no_attachments_is_missing_attachment():
    assert (
        check_escalation(attachments=[], si_fields={}, bl_fields={})
        is ReviewReason.MISSING_ATTACHMENT
    )


def test_si_only_is_missing_attachment():
    """email_507/509: the SI arrived, the draft BL did not."""
    assert (
        check_escalation(
            attachments=["attachments/email_507_SI.txt"],
            si_fields=COMPLETE,
            bl_fields={},
        )
        is ReviewReason.MISSING_ATTACHMENT
    )


# --- unreadable (email_511-515) --------------------------------------------


def test_unreadable_document_is_unreadable():
    assert (
        check_escalation(attachments=PAIR, bl_readable=False, si_fields=COMPLETE)
        is ReviewReason.UNREADABLE
    )


def test_unreadable_outranks_wrong_doc_type():
    """You cannot judge a document's type before you can read it."""
    assert (
        check_escalation(
            attachments=PAIR, bl_readable=False, bl_is_bill_of_lading=False
        )
        is ReviewReason.UNREADABLE
    )


# --- wrong_doc_type (email_501-505) ----------------------------------------


def test_non_bl_second_document_is_wrong_doc_type():
    assert (
        check_escalation(
            attachments=PAIR,
            bl_is_bill_of_lading=False,
            si_fields=COMPLETE,
            bl_fields=COMPLETE,
        )
        is ReviewReason.WRONG_DOC_TYPE
    )


def test_wrong_doc_type_outranks_missing_value():
    """A Commercial Invoice has no shipping fields to be blank; reporting
    its absent fields as missing_value would hide what is actually wrong."""
    assert (
        check_escalation(
            attachments=PAIR,
            bl_is_bill_of_lading=False,
            si_fields=COMPLETE,
            bl_fields={},
        )
        is ReviewReason.WRONG_DOC_TYPE
    )


# --- missing_value (email_516-520) -----------------------------------------


def test_blank_value_is_missing_value():
    assert (
        check_escalation(
            attachments=PAIR,
            si_fields={**COMPLETE, "port_of_discharge": ""},
            bl_fields=COMPLETE,
        )
        is ReviewReason.MISSING_VALUE
    )


def test_blank_on_the_bl_side_is_also_missing_value():
    assert (
        check_escalation(
            attachments=PAIR,
            si_fields=COMPLETE,
            bl_fields={**COMPLETE, "consignee": ""},
        )
        is ReviewReason.MISSING_VALUE
    )


def test_field_absent_from_one_side_is_missing_value():
    partial = {k: v for k, v in COMPLETE.items() if k != "gross_weight_kg"}
    assert (
        check_escalation(attachments=PAIR, si_fields=COMPLETE, bl_fields=partial)
        is ReviewReason.MISSING_VALUE
    )


# --- BL sniffing -----------------------------------------------------------


def test_genuine_bill_of_lading_is_recognised():
    assert looks_like_bill_of_lading("BILL OF LADING (DRAFT)\nB/L No: SIN2609887\n")


def test_company_headed_bill_of_lading_is_recognised():
    """The xlsx/docx BLs lead with the company name and carry the BL number
    on line 2."""
    assert looks_like_bill_of_lading(
        "ASIA PACIFIC PAPERBOARD TRADING PTE LTD\nBILL OF LADING: 3154303911\n"
    )


def test_commercial_invoice_is_rejected():
    assert not looks_like_bill_of_lading(
        "COMMERCIAL INVOICE\n\nInvoice No.: 5250078266\nSeller: APRIL FINE PAPER\n"
    )


def test_packing_list_is_rejected_despite_shipping_labels():
    """email_502/504 carry Shipper and Consignee, so structure alone would
    pass them. The title is what gives them away."""
    text = (
        "PACKING LIST\n\nShipper: ASIA PACIFIC PAPERBOARD TRADING PTE LTD\n"
        "Consignee: ROXCEL TRADING GMBH\nBooking Ref: MCLSINJEA2508070\n"
    )
    fields = {"shipper": "ASIA PACIFIC", "consignee": "ROXCEL TRADING GMBH"}
    assert not looks_like_bill_of_lading(text, fields)


def test_certificate_of_origin_is_rejected():
    assert not looks_like_bill_of_lading(
        "CERTIFICATE OF ORIGIN\n\nExporter: APRIL FAR EAST (M) SDN BHD\n"
    )


def test_shipping_instruction_heading_is_not_a_bill_of_lading():
    """10 SI documents are headed 'BILL OF LADING INSTRUCTION'. That is an
    instruction to produce a BL, not a BL."""
    assert not looks_like_bill_of_lading("BILL OF LADING INSTRUCTION\n", {})


# --- expects_comparison ----------------------------------------------------


def test_request_to_send_a_draft_is_not_a_failed_comparison():
    """91 real emails read like this. Flagging them missing_attachment would
    put 96 emails in the review queue where the dataset intends 5."""
    assert not expects_comparison(
        {
            "subject": "RE_ TO CONFIRM DOCS _ 5AAT-03056 _ AQABA_JORDAN",
            "body": "Please assist to send the draft BL for SIN832764835 for checking asap.",
            "attachments": [],
        }
    )


def test_request_to_compare_with_dropped_attachments_is_a_failed_comparison():
    """email_506/508/510."""
    assert expects_comparison(
        {
            "subject": "RE_ AFRT - LONG BEACH_US",
            "body": (
                "Please compare the SI and draft BL for 070500263211 and confirm "
                "(attachments appear to have been dropped). Thank you."
            ),
            "attachments": [],
        }
    )


def test_security_banner_mentioning_attachments_does_not_count():
    """27 of the 'assist to send' emails carry a banner reading 'please
    exercise caution with attachments'. A bare match on 'attach' would read
    every one of them as claiming an attachment."""
    assert not expects_comparison(
        {
            "subject": "TO CONFIRM DOCS _ 5SUS-42284",
            "body": (
                "WARNING: This email originated outside of our organisation. As a "
                "security measure, please exercise caution with attachments and "
                "links.\n\nPlease assist to send the draft BL for checking asap."
            ),
            "attachments": [],
        }
    )


def test_having_attachments_always_expects_a_comparison():
    assert expects_comparison({"subject": "", "body": "", "attachments": PAIR})


# --- attachment role detection ---------------------------------------------


def test_attachments_are_split_by_si_bl_naming():
    assert classify_attachments(PAIR) == (PAIR[0], PAIR[1])


def test_attachment_split_falls_back_to_position():
    pair = ["docs/first.pdf", "docs/second.pdf"]
    assert classify_attachments(pair) == (pair[0], pair[1])


def test_single_unnamed_attachment_has_no_second_document():
    assert classify_attachments(["docs/only.pdf"]) == ("docs/only.pdf", None)
