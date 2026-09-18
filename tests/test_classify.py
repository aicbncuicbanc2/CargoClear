"""Stage 1 tests.

These exercise the deterministic rule layer only — no Gemini calls, so the
suite runs offline and without an API key. Subject lines follow the
generator patterns documented in the dataset README and classify.py.
"""

from __future__ import annotations

from app.pipeline.classify import CONFIDENCE_FLOOR, classify_email, score_categories
from app.pipeline.models import Category


def email(subject: str = "", body: str = "", attachments=None) -> dict:
    return {
        "email_id": "email_test",
        "subject": subject,
        "body": body,
        "sender": "ops@example.com",
        "attachments": attachments or [],
    }


def test_email_004_classifies_as_bl_comparison():
    """The hand-traced email from docs/manual-trace-email_004.md."""
    category, confidence = classify_email(
        email(
            subject="REQUEST BL DRAFT _ PO 26067_ COATED IVORY BOARD__138MT",
            body="Please check the details and confirm against the attached SI.",
            attachments=["email_004_SI.txt", "email_004_BL.txt"],
        )
    )
    assert category == Category.BL_COMPARISON
    assert confidence >= CONFIDENCE_FLOOR


def test_to_confirm_docs_is_bl_comparison():
    category, _ = classify_email(
        subject_email := email(
            subject="TO CONFIRM DOCS - MSC SINGAPORE",
            body="Kindly verify the draft B/L against the shipping instruction.",
            attachments=["email_112_SI.txt", "email_112_BL.txt"],
        )
    )
    assert subject_email  # fixture sanity
    assert category == Category.BL_COMPARISON


def test_si_request_is_not_confused_with_bl_comparison():
    """Both mention SI; only one carries documents to compare."""
    category, _ = classify_email(
        email(
            subject="REQUEST SI - SINI2609 - DIRECT(ONE) - KRPUS - ORIGINAL",
            body="Please send us the SI for the booking below.",
            attachments=[],
        )
    )
    assert category == Category.SI_REQUEST


def test_cust_si_is_si_request():
    category, _ = classify_email(
        email(subject="CUST SI _ BOOKING 88213", body="SI needed by cut-off.")
    )
    assert category == Category.SI_REQUEST


def test_invoice_query():
    category, _ = classify_email(
        email(
            subject="BILLING - MISSING GR FOR INVOICE 4471",
            body="We cannot trace the local charges on this invoice.",
        )
    )
    assert category == Category.INVOICE_QUERY


def test_dd_charges_is_invoice_query():
    category, _ = classify_email(
        email(subject="D & D charges dispute", body="Demurrage billed twice.")
    )
    assert category == Category.INVOICE_QUERY


def test_general_bot_notice():
    category, _ = classify_email(
        email(
            subject="_RPA_ UPDATE SUMMARY 18/09",
            body="Automated run completed. Do not reply to this message.",
        )
    )
    assert category == Category.GENERAL


def test_general_berthing_report():
    category, _ = classify_email(
        email(subject="Berthing Report - Port Klang", body="Vessel berthed 0600 hrs.")
    )
    assert category == Category.GENERAL


def test_spam_prize():
    category, _ = classify_email(
        email(
            subject="Congratulations! You have won a prize",
            body="Claim your reward now, click here to verify your account.",
        )
    )
    assert category == Category.SPAM


def test_spam_parcel_fee():
    category, _ = classify_email(
        email(
            subject="Your parcel is pending - customs fee required",
            body="Pay the small parcel fee to release your package.",
        )
    )
    assert category == Category.SPAM


def test_si_plus_bl_attachments_push_toward_comparison():
    """Structural signal: carrying both documents is what defines the task."""
    with_docs = score_categories(
        email(subject="Docs attached", attachments=["e1_SI.txt", "e1_BL.txt"])
    )
    without = score_categories(email(subject="Docs attached", attachments=[]))
    assert with_docs[Category.BL_COMPARISON] > without[Category.BL_COMPARISON]


def test_empty_email_falls_back_without_crashing():
    category, confidence = classify_email(email())
    assert category in set(Category)
    assert confidence == 0.0


def test_classify_tolerates_missing_keys():
    category, _ = classify_email({"email_id": "email_x"})
    assert category in set(Category)
