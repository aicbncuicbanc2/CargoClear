"""Route tests for the three report screens.

These use a small synthetic inbox rather than the real bundle, so they run
without data/ and without reading 250 attachments. The dataset-backed
end-to-end assertions live in test_dataset_coverage.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.pipeline.models import Category, EmailReport, EmailResult, FieldValue, Status
from app.pipeline.pipeline import ProcessedEmail

# Captured before the autouse fixture below replaces it, so the caching
# test can exercise the real implementation.
REAL_GET_REPORTS = main.get_reports


def _processed(
    email_id: str,
    category: Category,
    status: Status = Status.OK,
    review_reason=None,
    defect_fields: list[str] | None = None,
    fields: list[FieldValue] | None = None,
    evidence: str = "",
    attachment_count: int = 2,
) -> ProcessedEmail:
    result = EmailResult(
        category=category,
        status=status,
        review_reason=review_reason,
        has_defect=bool(defect_fields),
        defect_fields=defect_fields or [],
    )
    report = EmailReport(
        email_id=email_id,
        subject=f"Subject for {email_id}",
        sender="ops@example.com",
        result=result,
        fields=fields or [],
        evidence=evidence,
    )
    return ProcessedEmail(
        report,
        si_excerpt="SI HEADER",
        bl_excerpt="BL HEADER",
        attachment_count=attachment_count,
    )


FIELDS = [
    FieldValue(
        field="shipper", si_value="ACME SDN BHD", bl_value="ACME SDN BHD", match=True
    ),
    FieldValue(
        field="consignee",
        si_value="EAST BRIGHT FZ-LLC",
        bl_value="UAB NOVAKOPA",
        match=False,
    ),
    FieldValue(field="notify_party", si_value="X", bl_value=None, match=None),
]

FIXTURE = {
    "email_001": _processed("email_001", Category.BL_COMPARISON, Status.OK),
    "email_004": _processed(
        "email_004",
        Category.BL_COMPARISON,
        Status.MISMATCH,
        defect_fields=["consignee", "notify_party"],
        fields=FIELDS,
        evidence="consignee: SI has 'EAST BRIGHT FZ-LLC', BL has 'UAB NOVAKOPA'",
    ),
    "email_501": _processed(
        "email_501",
        Category.BL_COMPARISON,
        Status.NEEDS_REVIEW,
        review_reason="wrong_doc_type",
        evidence="The second attachment is not a Bill of Lading.",
    ),
    "email_008": _processed("email_008", Category.SI_REQUEST, attachment_count=0),
    "email_026": _processed("email_026", Category.SPAM),
}


@pytest.fixture(autouse=True)
def fixed_reports(monkeypatch):
    """Serve the routes from a known in-memory inbox.

    Patches the cache loader, so no test ever triggers a real inbox run (or
    a Gemini call) through the web layer.
    """
    monkeypatch.setattr(main, "get_reports", lambda refresh=False: FIXTURE)


@pytest.fixture
def client():
    return TestClient(main.app)


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_health_alias(client):
    """On Cloud Run's *.run.app domains /healthz is intercepted by Google's
    edge and never reaches the container, so the service also answers on
    /health. Probe that one in production."""
    assert client.get("/health").json() == {"status": "ok"}


def test_inbox_lists_every_email(client):
    body = client.get("/").text
    assert "Showing 5 of 5 emails." in body
    for email_id in FIXTURE:
        assert f"/email/{email_id}" in body


def test_inbox_stats_header(client):
    body = client.get("/").text
    stats = main.build_stats(FIXTURE)
    assert stats == {"total": 5, "comparisons": 3, "mismatches": 1, "escalated": 1}
    assert ">5</h3>" in body and "Emails processed" in body
    assert "Comparison requests" in body
    assert "Mismatches found" in body
    assert "Escalated for review" in body


def test_inbox_shows_attachment_count_not_a_timestamp():
    """The dataset has no timestamp field, so the column reports the real
    attachment count rather than a fabricated date."""
    row = main._as_row(FIXTURE["email_004"])
    assert row["attachment_count"] == 2
    assert "timestamp" not in row


def test_inbox_table_renders_the_attachment_column(client):
    body = client.get("/").text
    assert "<th>Attachments</th>" in body
    assert "<th>Timestamp</th>" not in body


def test_email_with_no_attachments_shows_zero(client):
    assert main._as_row(FIXTURE["email_008"])["attachment_count"] == 0


def test_filter_by_category(client):
    body = client.get("/", params={"category": "BL_COMPARISON"}).text
    assert "Showing 3 of 5 emails." in body
    assert "/email/email_008" not in body


def test_filter_by_status(client):
    body = client.get("/", params={"status": "MISMATCH"}).text
    assert "Showing 1 of 5 emails." in body
    assert "/email/email_004" in body


def test_filters_combine(client):
    body = client.get(
        "/", params={"category": "BL_COMPARISON", "status": "NEEDS_REVIEW"}
    ).text
    assert "Showing 1 of 5 emails." in body
    assert "/email/email_501" in body


def test_filter_with_no_matches_is_not_an_error(client):
    response = client.get("/", params={"category": "INVOICE_QUERY"})
    assert response.status_code == 200
    assert "No emails match this filter." in response.text


# --- status colour coding --------------------------------------------------


def test_non_comparison_email_is_gray_not_green():
    """An SI_REQUEST is OK because no comparison was requested, not because
    documents agreed — colouring it green would overstate the check."""
    assert main.status_badge("OK", "SI_REQUEST") == "badge-na"
    assert main.status_badge("OK", "BL_COMPARISON") == "badge-match"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("OK", "badge-match"),
        ("MISMATCH", "badge-mismatch"),
        ("NEEDS_REVIEW", "badge-review"),
    ],
)
def test_comparison_status_colours(status, expected):
    assert main.status_badge(status, "BL_COMPARISON") == expected


# --- detail view -----------------------------------------------------------


def test_detail_shows_mismatched_and_matching_rows(client):
    body = client.get("/email/email_004").text
    assert "2 mismatch(es) detected:" in body
    assert "row-mismatch" in body and "row-match" in body
    assert "EAST BRIGHT FZ-LLC" in body and "UAB NOVAKOPA" in body


def test_detail_shows_no_mismatch_banner_when_ok(client):
    body = client.get("/email/email_001").text
    assert "No mismatch detected." in body


def test_detail_shows_evidence_and_source_excerpt(client):
    body = client.get("/email/email_004").text
    assert "SI HEADER" in body and "BL HEADER" in body
    assert "Evidence" in body


def test_detail_for_non_comparison_email(client):
    body = client.get("/email/email_008").text
    assert "Not a document comparison request." in body
    assert "No mismatch detected." not in body


def test_detail_marks_uncomparable_field_as_not_stated(client):
    body = client.get("/email/email_004").text
    assert "(not stated)" in body
    assert "not comparable" in body


def test_unknown_email_is_404(client):
    response = client.get("/email/does_not_exist")
    assert response.status_code == 404
    assert "Email not found" in response.text


# --- review queue ----------------------------------------------------------


def test_review_queue_lists_only_escalations(client):
    body = client.get("/review").text
    assert "1 email(s) could not be compared" in body
    assert "/email/email_501" in body
    assert "/email/email_004" not in body


def test_review_queue_shows_reason_and_evidence(client):
    body = client.get("/review").text
    assert "wrong_doc_type" in body
    assert "The second attachment is not a Bill of Lading." in body


def test_empty_review_queue_reads_cleanly(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "get_reports",
        lambda refresh=False: {"email_008": FIXTURE["email_008"]},
    )
    body = client.get("/review").text
    assert "Nothing in the review queue" in body


# --- caching ---------------------------------------------------------------


def test_reports_are_computed_once(monkeypatch):
    """Running the pipeline per page load would make every request wait on
    250 file reads and the Gemini tail."""
    calls = {"n": 0}

    def fake_process_inbox(source):
        calls["n"] += 1
        return FIXTURE

    monkeypatch.setattr(main, "process_inbox", fake_process_inbox)
    monkeypatch.setattr(main, "_REPORTS", {})

    REAL_GET_REPORTS()
    REAL_GET_REPORTS()
    REAL_GET_REPORTS()
    assert calls["n"] == 1, "inbox was processed more than once"

    REAL_GET_REPORTS(refresh=True)
    assert calls["n"] == 2, "refresh=True did not recompute"


# --- the submission artifact ---------------------------------------------


def test_submission_route_serves_every_email(client):
    response = client.get("/submission.json")
    assert response.status_code == 200

    payload = response.json()
    assert set(payload) == set(FIXTURE)


def test_submission_route_matches_the_pipeline_shape(client):
    """What is downloadable must be exactly what would be submitted."""
    payload = client.get("/submission.json").json()
    expected = {
        email_id: processed.result.to_submission()
        for email_id, processed in FIXTURE.items()
    }
    assert payload == expected


def test_submission_route_downloads_as_a_file(client):
    response = client.get("/submission.json")
    assert "attachment" in response.headers["content-disposition"]
    assert "submission.json" in response.headers["content-disposition"]


# --- inbox search ---------------------------------------------------------


def test_search_matches_an_email_id(client):
    response = client.get("/", params={"q": "email_004"})
    assert response.status_code == 200
    assert "email_004" in response.text
    assert "email_001" not in response.text


def test_search_is_case_insensitive(client):
    assert "email_004" in client.get("/", params={"q": "EMAIL_004"}).text


def test_search_matches_the_subject(client):
    assert "email_004" in client.get("/", params={"q": "Subject for email_004"}).text


def test_search_with_no_match_shows_the_empty_state(client):
    response = client.get("/", params={"q": "no-such-email-anywhere"})
    assert response.status_code == 200
    assert "No emails match this filter." in response.text


def test_search_combines_with_the_category_filter(client):
    response = client.get(
        "/", params={"q": "email", "category": Category.BL_COMPARISON.value}
    )
    assert response.status_code == 200
    for email_id, processed in FIXTURE.items():
        if processed.result.category is not Category.BL_COMPARISON:
            assert f"/email/{email_id}" not in response.text
