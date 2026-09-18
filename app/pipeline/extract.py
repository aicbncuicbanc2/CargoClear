"""Stage 2: extract the 7 shipment fields from SI / BL attachment text.

Placeholder for now — filled in Sat 19 Sep per the build plan. Will use a
field-alias dictionary for known label synonyms first, falling back to
Gemini for ambiguous cases.

Attachments are a mix of formats (~78% .txt, ~22% real binary: pdf+pdf,
xlsx+docx, xlsx+xlsx — see data/attachments). The .txt path can be parsed
directly; pdf/docx/xlsx need their own readers (pdfplumber / python-docx /
openpyxl) before the same alias matching applies.

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
"""

from app.pipeline.models import COMPARISON_FIELDS

# Known label synonyms seen across SI/BL documents. Lowercased, matched
# against a normalized (lowercased, punctuation-stripped) line prefix.
# Seed set from manually tracing email_004 + the dataset README; expect to
# extend this as more samples (esp. pdf/docx/xlsx) are traced Sat 19 Sep.
FIELD_ALIASES: dict[str, list[str]] = {
    "shipper": ["shipper"],
    "consignee": [
        "consignee",
        "consignee (non-negotiable)",
        "to the order of",
        "to order",
    ],
    "notify_party": ["notify", "notify party"],
    "port_of_loading": ["port of loading", "port of loading (pol)", "pol", "load port"],
    "port_of_discharge": [
        "port of discharge",
        "port of discharge (pod)",
        "pod",
        "discharge port",
    ],
    "container_count": ["total containers", "container count", "containers"],
    "gross_weight_kg": ["gross wt (kgs)", "gross weight (kg)", "gross weight", "gross wt"],
}

assert set(FIELD_ALIASES) == set(COMPARISON_FIELDS)


def extract_fields(document_text: str) -> dict[str, str | None]:
    raise NotImplementedError("extract_fields: to be built Sat 19 Sep")
