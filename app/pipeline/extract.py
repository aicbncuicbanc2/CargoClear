"""Stage 2: extract the 7 shipment fields from SI / BL attachment text.

Attachments are a mix of formats (~78% .txt, ~22% real binary: pdf+pdf,
xlsx+docx, xlsx+xlsx — see data/attachments). `read_document()` normalizes
every format down to label/value text lines, so exactly one alias matcher
serves all of them.

Label synonymy is deliberate in this dataset (SI vs BL use different labels
for the same field) — confirmed by manually tracing email_004:

    field            | SI label                      | BL label
    -----------------|--------------------------------|---------------------------
    shipper          | Shipper                        | SHIPPER
    consignee        | Consignee (Non-Negotiable)      | To the Order of
    notify_party      | Notify                         | Notify Party
    port_of_loading   | Port of Loading (POL)          | Port of Loading (POL)
    port_of_discharge | POD                            | POD
    container_count   | Total Containers               | Container Count
    gross_weight_kg   | Gross Wt (kgs)                 | Gross Weight (KG)

Also per the dataset README, expect: "Load Port" as another POL alias.

Matching is on the *normalized* label (lowercased, punctuation flattened to
spaces), and must be an exact whole-label match rather than a substring —
short aliases like "pol"/"pod" would otherwise fire inside unrelated labels
such as "Place of Delivery".
"""

from __future__ import annotations

import re
from pathlib import Path

from app.pipeline.models import COMPARISON_FIELDS


class UnreadableDocument(Exception):
    """Raised when a file yields no usable text (scanned image, 0 bytes,
    garbled). Stage 4 turns this into review_reason='unreadable'."""


# Known label synonyms seen across SI/BL documents. Lowercased, matched
# against a normalized (lowercased, punctuation-stripped) line prefix.
# Seed set from manually tracing email_004 + the dataset README.
FIELD_ALIASES: dict[str, list[str]] = {
    "shipper": [
        "shipper",
        "shippers",
        "shipper name",
        "shipper exporter",
        "exporter",
        "consignor",
    ],
    "consignee": [
        "consignee",
        "consignee (non-negotiable)",
        "consignee non negotiable",
        "to the order of",
        "to order of",
        "to order",
        "order of",
        "consigned to",
        "consignee name",
    ],
    "notify_party": [
        "notify",
        "notify party",
        "notify parties",
        "notify address",
        "party to notify",
        "also notify",
    ],
    "port_of_loading": [
        "port of loading",
        "port of loading (pol)",
        "pol",
        "load port",
        "loading port",
        "port of load",
        "place of receipt",
    ],
    "port_of_discharge": [
        "port of discharge",
        "port of discharge (pod)",
        "pod",
        "discharge port",
        "port of unloading",
        "place of delivery",
        "destination port",
    ],
    "container_count": [
        "total containers",
        "container count",
        "containers",
        "no of containers",
        "number of containers",
        "qty of containers",
        "container qty",
        "total container",
    ],
    "gross_weight_kg": [
        "gross wt (kgs)",
        "gross wt kgs",
        "gross weight (kg)",
        "gross weight kg",
        "gross weight",
        "gross wt",
        "total gross weight",
        "gross weight kgs",
        "gross mass",
    ],
}

assert set(FIELD_ALIASES) == set(COMPARISON_FIELDS)

# Values that mean "this was left blank", not "this is the value". These
# drive review_reason='missing_value' in stage 4 — never a mismatch.
BLANK_MARKERS = {
    "",
    "-",
    "--",
    "---",
    "n/a",
    "na",
    "nil",
    "none",
    "tba",
    "tbd",
    "tbc",
    "to be advised",
    "to be confirmed",
    "pending",
    "unknown",
    "?",
    "??",
    "???",
    "xxx",
    "xxxx",
}

# A label ends at the first colon, a tab, or a run of 2+ spaces (column
# layouts in fixed-width text and PDF extractions).
_SPLIT_RE = re.compile(r"^(?P<label>[^:\t]{1,60}?)\s*(?::|\t|\s{2,})\s*(?P<value>.*)$")


def normalize_label(label: str) -> str:
    """Flatten a label to its comparable form: lowercase, punctuation to
    spaces, whitespace collapsed. 'Gross Wt (kgs)' -> 'gross wt kgs'."""
    flattened = re.sub(r"[^0-9a-z]+", " ", label.lower())
    return re.sub(r"\s+", " ", flattened).strip()


# normalized alias -> (field, rank). Aliases are normalized with the same
# function as document labels so both sides agree by construction. Rank is
# the alias's position in its list: lists are written canonical-first, so a
# document carrying both "Place of Receipt" and "Port of Loading" resolves
# to the latter regardless of which appears first on the page.
_ALIAS_INDEX: dict[str, tuple[str, int]] = {}
for _field, _aliases in FIELD_ALIASES.items():
    for _rank, _alias in enumerate(_aliases):
        _ALIAS_INDEX[normalize_label(_alias)] = (_field, _rank)


def is_blank_value(value: str | None) -> bool:
    """True when a value is present in the document but carries no content
    (blank line, '???', '______', 'TBA')."""
    if value is None:
        return True
    stripped = value.strip()
    if stripped.lower() in BLANK_MARKERS:
        return True
    # Runs of fill characters used as write-in blanks: ____, ....., ----
    return bool(re.fullmatch(r"[_.\-*·\s]+", stripped))


def _looks_like_label(line: str) -> bool:
    """Does this line start a new labelled field (rather than continue the
    previous value)? Used to stop multi-line value capture."""
    match = _SPLIT_RE.match(line)
    if not match:
        return False
    return normalize_label(match.group("label")) in _ALIAS_INDEX


def extract_fields(document_text: str) -> dict[str, str | None]:
    """Pull the 7 comparison fields out of one document's text.

    All 7 keys are always present; a field is None when it is absent from
    the document or present-but-blank (both are stage 4's problem, not a
    mismatch). The first occurrence of a field wins — shipping documents
    repeat labels in footers and continuation pages.
    """
    fields: dict[str, str | None] = {field: None for field in COMPARISON_FIELDS}
    best_rank: dict[str, int] = {}

    lines = document_text.splitlines()
    for index, line in enumerate(lines):
        match = _SPLIT_RE.match(line)
        if not match:
            continue

        entry = _ALIAS_INDEX.get(normalize_label(match.group("label")))
        if entry is None:
            continue
        field, rank = entry
        # First occurrence wins (documents repeat labels in footers and
        # continuation pages) unless this label is a better-ranked alias.
        if field in best_rank and rank >= best_rank[field]:
            continue

        value = match.group("value").strip()

        # Block layout: "Consignee:" on its own line, value on the lines
        # below. Gather continuation lines until the next known label or a
        # blank line, capped so a runaway parse cannot swallow the document.
        if not value:
            collected: list[str] = []
            for following in lines[index + 1 : index + 5]:
                if not following.strip() or _looks_like_label(following):
                    break
                collected.append(following.strip())
            value = " ".join(collected).strip()

        best_rank[field] = rank
        fields[field] = None if is_blank_value(value) else value

    return fields


# --- format readers -------------------------------------------------------
# Each reader returns label/value text lines so extract_fields() can stay
# format-agnostic.


def read_document(path: str | Path) -> str:
    """Read any supported attachment into text.

    Raises UnreadableDocument for empty files, image-only scanned PDFs, and
    anything that yields no extractable text — stage 4 maps that to
    review_reason='unreadable'.
    """
    path = Path(path)
    if not path.exists():
        raise UnreadableDocument(f"{path} does not exist")
    if path.stat().st_size == 0:
        raise UnreadableDocument(f"{path} is empty (0 bytes)")

    suffix = path.suffix.lower()
    if suffix in {".txt", ".text", ".csv", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        text = _read_pdf(path)
    elif suffix in {".docx", ".doc"}:
        text = _read_docx(path)
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        text = _read_xlsx(path)
    else:
        raise UnreadableDocument(f"{path}: unsupported format '{suffix}'")

    if not text or not text.strip():
        raise UnreadableDocument(f"{path}: no extractable text (scanned or garbled?)")
    return text


def _read_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - environment issue
        raise UnreadableDocument("pdfplumber is not installed") from exc

    try:
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:
        raise UnreadableDocument(f"{path}: PDF could not be parsed ({exc})") from exc
    return "\n".join(pages)


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text_of(element) -> str:
    """Concatenated run text under one element (paragraph or cell)."""
    parts = [node.text or "" for node in element.iter(f"{_W_NS}t")]
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _read_docx(path: Path) -> str:
    """Read a .docx using only the standard library.

    A .docx is a zip whose word/document.xml holds the content, so this
    needs no third-party parser. That is deliberate: python-docx pulls in
    lxml, whose compiled _elementpath extension is blocked by Application
    Control policy on the dev machine — and a reader that only works on the
    deploy target is a reader that cannot be tested before deploying.
    """
    import zipfile
    from xml.etree import ElementTree

    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise UnreadableDocument(f"{path}: DOCX could not be parsed ({exc})") from exc

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise UnreadableDocument(f"{path}: DOCX XML is malformed ({exc})") from exc

    # Paragraphs living inside table cells are emitted as part of their row,
    # so they must not also be emitted standalone. ElementTree has no parent
    # links, so collect them up front.
    in_table = {
        id(paragraph)
        for row in root.iter(f"{_W_NS}tr")
        for paragraph in row.iter(f"{_W_NS}p")
    }

    lines: list[str] = []
    # Walk paragraphs and table rows in document order. Shipping docs put
    # most fields in tables: render each row as "label: value" so the same
    # alias matcher applies to tables and prose alike.
    for element in root.iter():
        if element.tag == f"{_W_NS}tr":
            cells = [
                text
                for cell in element.findall(f"{_W_NS}tc")
                if (text := _docx_text_of(cell))
            ]
            if len(cells) >= 2:
                lines.append(f"{cells[0]}: {' '.join(cells[1:])}")
            elif cells:
                lines.append(cells[0])
        elif element.tag == f"{_W_NS}p" and id(element) not in in_table:
            if text := _docx_text_of(element):
                lines.append(text)

    return "\n".join(lines)


def _read_xlsx(path: Path) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - environment issue
        raise UnreadableDocument("openpyxl is not installed") from exc

    try:
        workbook = load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise UnreadableDocument(f"{path}: XLSX could not be parsed ({exc})") from exc

    lines: list[str] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
            if len(cells) >= 2:
                lines.append(f"{cells[0]}: {' '.join(cells[1:])}")
            elif cells:
                lines.append(cells[0])
    workbook.close()
    return "\n".join(lines)


def extract_from_file(path: str | Path) -> dict[str, str | None]:
    """Convenience: read a document of any supported format and extract."""
    return extract_fields(read_document(path))
