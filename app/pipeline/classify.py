"""Stage 1: classify an inbox email into one of the 5 categories.

Categories (exact values the dataset expects) and the subject-line signals
observed in data_v2's generator, per the dataset README:

    BL_COMPARISON  (~40%) - "TO CONFIRM DOCS", "REQUEST BL DRAFT",
                             coded "AIE - POD - CARRIER(BL#) - OC - INV - CUSTOMER - TERM",
                             "Draft BL ... amend"
    SI_REQUEST     (~25%) - "SI - <bl> - DIRECT(<carrier>) - <OC> - <POD> - <BLtype>",
                             "CUST SI", "REQUEST SI", "SI NEEDED"
    INVOICE_QUERY  (~15%) - "BILLING ... MISSING GR", "CANCEL INVOICE",
                             "LOCAL CHARGES", "D & D charges", "Total Freight"
    GENERAL        (~12%) - "UPDATE SUMMARY", "Berthing Report", SLA reminders,
                             "_RPA_" bot notices, HR/holiday notices
    SPAM           (~8%)  - prize/parcel-fee/mailbox-full/phishing

Placeholder for now — filled in Sat 19 Sep per the build plan. Will call
Gemini with structured JSON output (category + confidence).
"""

from app.pipeline.models import Category


def classify_email(email: dict) -> tuple[Category, float]:
    raise NotImplementedError("classify_email: to be built Sat 19 Sep")
