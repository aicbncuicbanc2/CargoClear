"""Format-reader tests.

~22% of the dataset's attachment pairs are real binary files (pdf+pdf,
xlsx+docx, xlsx+xlsx). These build genuine .xlsx/.docx files on the fly and
push them through the same alias matcher the .txt path uses, so a format
regression surfaces here rather than mid-run on Sunday.

The PDF path is not covered here (no writer library in requirements); it is
exercised against the dataset's real pdf pairs.
"""

from __future__ import annotations

import pytest

from app.pipeline.extract import (
    UnreadableDocument,
    extract_from_file,
    read_document,
)

ROWS = [
    ("Shipper", "APRIL FAR EAST (M) SDN BHD"),
    ("To the Order of", "UAB NOVAKOPA"),
    ("Notify Party", "UAB NOVAKOPA"),
    ("Load Port", "NANTONG, CHINA (CNNTG)"),
    ("Discharge Port", "KARACHI, PAKISTAN (PKKHI)"),
    ("Container Count", "6 x 40'HC"),
    ("Gross Weight (KG)", "131,058 KG"),
]

EXPECTED = {
    "shipper": "APRIL FAR EAST (M) SDN BHD",
    "consignee": "UAB NOVAKOPA",
    "notify_party": "UAB NOVAKOPA",
    "port_of_loading": "NANTONG, CHINA (CNNTG)",
    "port_of_discharge": "KARACHI, PAKISTAN (PKKHI)",
    "container_count": "6 x 40'HC",
    "gross_weight_kg": "131,058 KG",
}


def test_xlsx_rows_become_label_value_lines(tmp_path):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["BILL OF LADING (DRAFT)"])
    for label, value in ROWS:
        sheet.append([label, value])
    path = tmp_path / "email_900_BL.xlsx"
    workbook.save(path)

    assert extract_from_file(path) == EXPECTED


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def _write_docx(path, body_xml: str) -> None:
    """Build a .docx containing the given body XML.

    Written with the stdlib rather than python-docx: that library needs
    lxml, whose compiled extension is blocked by Application Control policy
    on this machine. A .docx is a zip and the reader only consumes
    word/document.xml, so this produces exactly what it parses.
    """
    import zipfile

    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{body_xml}</w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def test_docx_table_rows_are_read(tmp_path):
    rows = "".join(
        f"<w:tr><w:tc>{_paragraph(label)}</w:tc><w:tc>{_paragraph(value)}</w:tc></w:tr>"
        for label, value in ROWS
    )
    body = _paragraph("BILL OF LADING (DRAFT)") + f"<w:tbl>{rows}</w:tbl>"
    path = tmp_path / "email_900_BL.docx"
    _write_docx(path, body)

    assert extract_from_file(path) == EXPECTED


def test_docx_paragraph_layout_is_read(tmp_path):
    body = "".join(_paragraph(f"{label}: {value}") for label, value in ROWS)
    path = tmp_path / "email_901_BL.docx"
    _write_docx(path, body)

    assert extract_from_file(path) == EXPECTED


def test_docx_table_cell_text_is_not_emitted_twice(tmp_path):
    """A cell's paragraphs must not also appear as standalone lines, or a
    bare label line could capture the wrong value as a block layout."""
    rows = (
        f"<w:tr><w:tc>{_paragraph('Shipper')}</w:tc>"
        f"<w:tc>{_paragraph('APRIL FAR EAST (M) SDN BHD')}</w:tc></w:tr>"
    )
    path = tmp_path / "email_906_BL.docx"
    _write_docx(path, f"<w:tbl>{rows}</w:tbl>")

    text = read_document(path)
    assert text.strip() == "Shipper: APRIL FAR EAST (M) SDN BHD"


def test_docx_line_breaks_are_preserved(tmp_path):
    """A <w:br/> inside a run is a real line break. Concatenating runs welds
    the party name onto its address ('...TRADINGON BEHALF OF...'), which
    both corrupts the name and defeats the first-line rule. Taken from
    email_055_BL.docx."""
    cell = (
        "<w:p><w:r>"
        "<w:t>APRIL FINE PAPER TRADING</w:t><w:br/>"
        "<w:t>ON BEHALF OF VITAL SOLUTIONS PTE LTD</w:t><w:br/>"
        "<w:t>77 ROBINSON ROAD, #21-01</w:t>"
        "</w:r></w:p>"
    )
    label = _paragraph("Shipper (Principal or Seller) (发货人)")
    path = tmp_path / "email_909_BL.docx"
    _write_docx(path, f"<w:tbl><w:tr><w:tc>{label}</w:tc><w:tc>{cell}</w:tc></w:tr></w:tbl>")

    text = read_document(path)
    assert "TRADINGON" not in text
    assert extract_from_file(path)["shipper"] == "APRIL FINE PAPER TRADING"


def test_xlsx_pipe_separated_cell_splits_into_lines(tmp_path):
    """The .xlsx pairs pack name and address into one cell separated by '|',
    the same structure the .docx pairs express with <w:br/>. Both must
    reduce to the same first line or the pair compares unequal."""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        ["Shipper/Exporter", "APRIL FINE PAPER TRADING | ON BEHALF OF VITAL SOLUTIONS"]
    )
    path = tmp_path / "email_910_SI.xlsx"
    workbook.save(path)

    assert extract_from_file(path)["shipper"] == "APRIL FINE PAPER TRADING"


def test_docx_missing_document_xml_is_unreadable(tmp_path):
    import zipfile

    path = tmp_path / "email_907_BL.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/settings.xml", "<x/>")
    with pytest.raises(UnreadableDocument):
        read_document(path)


def test_garbled_docx_raises_rather_than_crashing(tmp_path):
    path = tmp_path / "email_908_BL.docx"
    path.write_bytes(b"not actually a word document")
    with pytest.raises(UnreadableDocument):
        read_document(path)


def test_empty_file_is_unreadable(tmp_path):
    path = tmp_path / "email_902_BL.txt"
    path.write_text("")
    with pytest.raises(UnreadableDocument):
        read_document(path)


def test_whitespace_only_file_is_unreadable(tmp_path):
    path = tmp_path / "email_903_BL.txt"
    path.write_text("   \n\n   \n")
    with pytest.raises(UnreadableDocument):
        read_document(path)


def test_missing_file_is_unreadable(tmp_path):
    with pytest.raises(UnreadableDocument):
        read_document(tmp_path / "does_not_exist.txt")


def test_unsupported_format_is_unreadable(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    with pytest.raises(UnreadableDocument):
        read_document(path)


def test_garbled_xlsx_raises_rather_than_crashing(tmp_path):
    path = tmp_path / "email_904_BL.xlsx"
    path.write_bytes(b"not actually a spreadsheet")
    with pytest.raises(UnreadableDocument):
        read_document(path)


def test_txt_reader_tolerates_bad_encoding_bytes(tmp_path):
    path = tmp_path / "email_905_SI.txt"
    path.write_bytes("Shipper: CAFÉ EXPORTS\n".encode("latin-1"))
    fields = extract_from_file(path)
    assert fields["shipper"] is not None
    assert "EXPORTS" in fields["shipper"]
