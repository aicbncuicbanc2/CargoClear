"""Integration checks against the real dataset.

data/ is gitignored, so these skip automatically on a fresh clone. When the
bundle is present they are the guard that an alias or reader change has not
quietly lost coverage — the unit tests pin specific known lines, this pins
the aggregate over all 242 readable documents.

Thresholds are floors, not targets: they should only ever be raised.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.pipeline.extract import UnreadableDocument, extract_fields, read_document
from app.pipeline.models import COMPARISON_FIELDS

DATA = Path(__file__).resolve().parent.parent / "data"

pytestmark = pytest.mark.skipif(
    not (DATA / "inbox").is_dir(),
    reason="dataset bundle not present (data/ is gitignored)",
)


def _inbox():
    sys.path.insert(0, str(DATA))
    from loader import Inbox

    return Inbox(str(DATA))


# The 20 purpose-built edge cases are *meant* to fail extraction; they carry
# wrong document types, missing attachments, unreadable scans or blank values.
EDGE_CASE_IDS = {f"email_{n}" for n in range(501, 521)}


def _is_edge_case(attachment_path: str) -> bool:
    return any(eid in attachment_path for eid in EDGE_CASE_IDS)


def test_every_main_document_extracts_all_seven_fields():
    """Outside the edge cases, extraction must be complete — no exceptions."""
    incomplete = []
    for email in _inbox():
        for attachment in email["attachments"]:
            if _is_edge_case(attachment):
                continue
            try:
                fields = extract_fields(read_document(DATA / attachment))
            except UnreadableDocument as exc:  # pragma: no cover - would be a bug
                incomplete.append((attachment, f"unreadable: {exc}"))
                continue
            missing = [f for f in COMPARISON_FIELDS if fields[f] is None]
            if missing:
                incomplete.append((attachment, missing))
    assert not incomplete, f"{len(incomplete)} documents incomplete: {incomplete[:5]}"


def test_all_four_binary_formats_are_exercised():
    """Guards against a reader silently regressing to zero coverage."""
    seen: dict[str, int] = {}
    for email in _inbox():
        for attachment in email["attachments"]:
            if _is_edge_case(attachment):
                continue
            suffix = Path(attachment).suffix.lower()
            try:
                fields = extract_fields(read_document(DATA / attachment))
            except UnreadableDocument:
                continue
            if all(fields[f] is not None for f in COMPARISON_FIELDS):
                seen[suffix] = seen.get(suffix, 0) + 1
    # Current state: every non-edge-case document of every format extracts
    # all 7 fields, so each floor is that format's full count.
    for suffix, floor in {".txt": 168, ".pdf": 20, ".xlsx": 22, ".docx": 8}.items():
        assert seen.get(suffix, 0) >= floor, f"{suffix}: {seen.get(suffix, 0)} < {floor}"


def test_unreadable_pdfs_are_confined_to_the_edge_cases():
    """email_511-515 are the purpose-built unreadable group. A reader
    regression would show up as unreadable files outside that range."""
    unreadable = []
    for email in _inbox():
        for attachment in email["attachments"]:
            try:
                read_document(DATA / attachment)
            except UnreadableDocument:
                unreadable.append(attachment)
    assert all(_is_edge_case(path) for path in unreadable), unreadable


def test_email_004_matches_the_hand_trace():
    """End-to-end against docs/manual-trace-email_004.md, the one pair
    verified by hand against the real files."""
    si = extract_fields(read_document(DATA / "attachments/email_004_SI.txt"))
    bl = extract_fields(read_document(DATA / "attachments/email_004_BL.txt"))
    differing = sorted(f for f in COMPARISON_FIELDS if si[f] != bl[f])
    assert differing == ["consignee", "notify_party"]
    assert si["consignee"] == "EAST BRIGHT FZ-LLC"
    assert bl["consignee"] == "UAB NOVAKOPA"
    assert si["port_of_loading"] == bl["port_of_loading"] == "NANTONG, CHINA (CNNTG)"


def test_classification_mix_tracks_the_documented_distribution(monkeypatch):
    """No ground truth ships with the bundle, but the dataset README states
    the category mix. A rule change that breaks a whole class shows up as a
    large deviation from it. Tolerance is wide because the README's figures
    are themselves approximate ("~40%"); this catches breakage, not drift."""
    import app.pipeline.classify as classify

    monkeypatch.setattr(classify, "classify_with_gemini", lambda email: None)

    documented = {
        "BL_COMPARISON": 40,
        "SI_REQUEST": 25,
        "INVOICE_QUERY": 15,
        "GENERAL": 12,
        "SPAM": 8,
    }
    counts: dict[str, int] = {name: 0 for name in documented}
    total = 0
    for email in _inbox():
        category, _ = classify.classify_email(email)
        counts[category.value] += 1
        total += 1

    assert total == 520
    for name, expected in documented.items():
        actual = 100 * counts[name] / total
        assert abs(actual - expected) <= 6, f"{name}: {actual:.1f}% vs ~{expected}%"


def test_most_emails_are_classified_without_calling_gemini(monkeypatch):
    """The free-tier quota is the constraint: the rule layer must carry the
    bulk of the inbox, with Gemini reserved for the ambiguous tail."""
    import app.pipeline.classify as classify

    monkeypatch.setattr(classify, "classify_with_gemini", lambda email: None)

    deferred = sum(
        1
        for email in _inbox()
        if classify.classify_email(email)[1] < classify.CONFIDENCE_FLOOR
    )
    assert deferred / 520 <= 0.15, f"{deferred}/520 would call Gemini"


def test_pairs_are_not_systematically_mismatched():
    """A parsing artifact that leaks into values (a stray '): ' prefix, a
    CJK gloss) shows up as nearly every pair differing. Real defects affect
    a minority of fields, so a floor on clean pairs catches that class of
    bug that per-document completeness cannot."""
    pairs = clean = 0
    for email in _inbox():
        attachments = email["attachments"]
        si = [a for a in attachments if "_SI." in a]
        bl = [a for a in attachments if "_BL." in a]
        if not si or not bl or _is_edge_case(attachments[0]):
            continue
        try:
            si_fields = extract_fields(read_document(DATA / si[0]))
            bl_fields = extract_fields(read_document(DATA / bl[0]))
        except UnreadableDocument:
            continue
        pairs += 1
        if all(si_fields[f] == bl_fields[f] for f in COMPARISON_FIELDS):
            clean += 1
    assert pairs >= 100, pairs
    assert clean / pairs >= 0.5, f"only {clean}/{pairs} pairs agree on all 7 fields"
