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

Strategy: deterministic weighted scoring over the signals above runs first —
it is free, instant, and reproducible, which matters because ~40% of the
inbox is BL_COMPARISON and every one of those drives the expensive
extract/compare path. Gemini is consulted only when the rules are not
confident enough to call it (see CONFIDENCE_FLOOR), keeping free-tier quota
for the genuinely ambiguous minority.

Subject lines carry far more signal than bodies in this dataset (the
generator builds them from templates), so subject hits are weighted heavier
than body hits.
"""

from __future__ import annotations

import re

from app.pipeline.models import Category

# Below this confidence the rule layer defers to Gemini rather than guessing.
CONFIDENCE_FLOOR = 0.45

SUBJECT_WEIGHT = 3.0
BODY_WEIGHT = 1.0

# Signal patterns per category. Matched case-insensitively against the
# normalized subject and body. Weights reflect how uniquely a phrase
# identifies its category: a coded subject pattern is decisive, a bare
# mention of "invoice" is weak because it appears across categories.
SIGNALS: dict[Category, list[tuple[str, float]]] = {
    Category.BL_COMPARISON: [
        (r"\bto confirm docs?\b", 3.0),
        (r"\brequest bl draft\b", 3.0),
        (r"\bdraft\s+b/?l\b", 2.5),
        (r"\bb/?l\s+draft\b", 2.5),
        (r"\bcheck(?:ing)?\s+(?:the\s+)?(?:details|draft|docs?)\b", 1.5),
        (r"\bconfirm\s+(?:the\s+)?(?:details|draft|docs?)\b", 1.5),
        (r"\bamend(?:ment)?\b", 1.2),
        (r"\bverify\b", 1.0),
        (r"\bagainst\s+(?:the\s+)?si\b", 2.0),
        (r"\bsi\s+(?:vs\.?|and)\s+b/?l\b", 2.5),
        # Coded subject: AIE - POD - CARRIER(BL#) - OC - INV - CUSTOMER - TERM
        (r"\baie\b\s*-\s*\w+\s*-\s*.+\(\s*\w*\d+\w*\s*\)", 3.0),
    ],
    Category.SI_REQUEST: [
        (r"\bcust\s+si\b", 3.0),
        (r"\brequest\s+si\b", 3.0),
        (r"\bsi\s+needed\b", 3.0),
        (r"\bshipping\s+instruction", 2.0),
        (r"\bsubmit\s+(?:the\s+)?si\b", 2.5),
        (r"\bsend\s+(?:us\s+)?(?:the\s+)?si\b", 2.5),
        (r"\bsi\s+submission\b", 2.5),
        # Coded subject: SI - <bl> - DIRECT(<carrier>) - <OC> - <POD> - <BLtype>
        (r"^\s*si\s*-\s*\S+\s*-\s*direct\s*\(", 3.5),
        (r"\bdirect\s*\([^)]+\)", 1.5),
    ],
    Category.INVOICE_QUERY: [
        (r"\bcancel\s+invoice\b", 3.0),
        (r"\bbilling\b", 2.0),
        (r"\bmissing\s+gr\b", 3.0),
        (r"\blocal\s+charges?\b", 2.5),
        (r"\bd\s*&\s*d\s+charges?\b", 3.0),
        (r"\bdemurrage\b", 2.0),
        (r"\bdetention\b", 2.0),
        (r"\btotal\s+freight\b", 2.5),
        (r"\binvoice\b", 1.5),
        (r"\bcredit\s+note\b", 2.0),
        (r"\bpayment\b", 1.0),
        (r"\boverchar\w+\b", 2.0),
    ],
    Category.GENERAL: [
        (r"\bupdate\s+summary\b", 3.0),
        # Decisive wherever it appears, subject or body: a berthing report is
        # always a routine operational notice. 11 emails in this inbox pair a
        # "Reminder ... Submit SI & AED" subject with a berthing-report body,
        # and the subject alone would drag them into SI_REQUEST.
        (r"\bberthing\s+report\b", 5.0),
        # Written "_RPA_" in the source; _text_of has flattened the
        # underscores to spaces by the time this runs.
        (r"\brpa\b", 3.0),
        (r"\bdear\s+colleagues\b", 2.0),
        (r"\boffice\s+resumes\b", 2.5),
        (r"\blist\s+of\s+outstanding\b", 2.0),
        (r"\btime\s+off\s+request\b", 2.5),
        (r"\bapproval\s+required\b", 1.5),
        (r"\bnew\s+year\b", 1.2),
        (r"\bsla\b", 2.0),
        (r"\breminder\b", 1.2),
        (r"\bpublic\s+holiday\b", 2.5),
        (r"\bholiday\s+notice\b", 2.5),
        (r"\bout\s+of\s+office\b", 2.5),
        (r"\bhr\b", 1.5),
        (r"\btraining\b", 1.2),
        (r"\bmaintenance\s+window\b", 2.0),
        (r"\bweekly\s+(?:report|summary|update)\b", 2.0),
        (r"\bdo\s+not\s+reply\b", 1.5),
    ],
    Category.SPAM: [
        (r"\byou(?:'ve|\s+have)\s+won\b", 3.5),
        (r"\bcongratulations\b", 2.0),
        (r"\bprize\b", 3.0),
        (r"\blottery\b", 3.5),
        (r"\bclaim\s+your\b", 2.5),
        (r"\bparcel\s+(?:fee|pending|held|customs\s+fee)\b", 3.0),
        (r"\bmailbox\s+(?:is\s+)?full\b", 3.0),
        (r"\bstorage\s+(?:is\s+)?(?:almost\s+)?full\b", 2.5),
        (r"\bverify\s+your\s+(?:account|password|identity)\b", 3.0),
        (r"\bclick\s+here\s+(?:to|now)\b", 2.0),
        (r"\baccount\s+(?:will\s+be\s+)?suspend\w*\b", 3.0),
        (r"\bunusual\s+(?:sign-?in|login|activity)\b", 2.5),
        (r"\bcrypto\w*\b", 2.0),
        (r"\bbitcoin\b", 2.5),
        (r"\bwire\s+transfer\s+urgent\b", 2.5),
        (r"\bgift\s+card\b", 2.5),
        (r"\bunsubscribe\b", 0.8),
        # Advertising spam: the phishing patterns above missed this whole
        # half of the SPAM class, which was landing in GENERAL with no
        # signal at all ("Hot singles...", "...ONE weird trick").
        (r"\blimited\s+time\s+offer\b", 3.0),
        (r"\bexclusive\s+offer\b", 3.0),
        (r"\bweird\s+trick\b", 3.5),
        (r"\bhot\s+singles\b", 3.5),
        (r"\bdear\s+valued\s+customer\b", 3.0),
        (r"\b\d{1,3}\s*%\s*off\b", 3.0),
        (r"\bbuy\s+now\b", 2.5),
        (r"\bdeal\s+expires\b", 2.5),
        (r"\bact\s+now\b", 2.0),
        (r"\btrusted\s+by\s+[\d,]+\+?\s*(?:companies|customers|clients)\b", 2.5),
        (r"\brisk[-\s]free\b", 2.0),
    ],
}

_COMPILED: dict[Category, list[tuple[re.Pattern[str], float]]] = {
    category: [(re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in signals]
    for category, signals in SIGNALS.items()
}


def _text_of(email: dict, *keys: str) -> str:
    """Read the first present key, tolerating loader naming differences.

    The dataset's loader.py hands back plain dicts; the exact key spelling
    ("body" vs "text", "sender" vs "from") is not worth coupling to.

    Underscores are flattened to spaces because this inbox uses "_" as a
    subject delimiter — "RE_ SI NEEDED_ 5APH-26773 _ UAB NOVAKOPA". An
    underscore is a word character to the regex engine, so "\\bsi needed\\b"
    does not match "SI NEEDED_" and the email lands in the wrong category.
    """
    for key in keys:
        value = email.get(key)
        if isinstance(value, str) and value.strip():
            return value.replace("_", " ")
    return ""


def _attachment_names(email: dict) -> list[str]:
    raw = email.get("attachments") or []
    names: list[str] = []
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("filename") or item.get("name") or item.get("path")
            if isinstance(name, str):
                names.append(name)
    return names


def score_categories(email: dict) -> dict[Category, float]:
    """Weighted signal score per category. Exposed for tuning/tests."""
    subject = _text_of(email, "subject", "title")
    body = _text_of(email, "body", "text", "content")

    scores: dict[Category, float] = {category: 0.0 for category in Category}

    for category, patterns in _COMPILED.items():
        total = 0.0
        for pattern, weight in patterns:
            if pattern.search(subject):
                total += weight * SUBJECT_WEIGHT
            if pattern.search(body):
                total += weight * BODY_WEIGHT
        scores[category] = total

    # Structural signal: a document-comparison request is defined by actually
    # carrying the two documents to compare. An SI attached *together with* a
    # BL means "check these against each other" (BL_COMPARISON), whereas an
    # SI_REQUEST is asking for an SI that does not exist yet.
    names = " ".join(_attachment_names(email)).lower()
    has_si = bool(re.search(r"(^|[^a-z])si([^a-z]|$)|shipping.?instruction", names))
    has_bl = bool(re.search(r"(^|[^a-z])b_?l([^a-z]|$)|bill.?of.?lading", names))

    if has_si and has_bl:
        scores[Category.BL_COMPARISON] += 6.0
    elif has_bl:
        scores[Category.BL_COMPARISON] += 2.0

    return scores


def classify_email(email: dict) -> tuple[Category, float]:
    """Return (category, confidence in 0..1).

    Confidence is the winning category's share of total signal, damped when
    the runner-up is close behind. Below CONFIDENCE_FLOOR the rules defer to
    Gemini; if Gemini is unavailable (no API key, quota, network) the rule
    verdict stands rather than failing the whole run — an uncertain label is
    still better than dropping the email.
    """
    scores = score_categories(email)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    runner_up_score = ranked[1][1]
    total = sum(scores.values())

    if total <= 0.0:
        # No signal at all: GENERAL is the dataset's catch-all for ordinary
        # correspondence, but flag it as unconfident so Gemini gets a look.
        return _fallback(email, Category.GENERAL, 0.0)

    share = best_score / total
    margin = (best_score - runner_up_score) / best_score if best_score else 0.0
    confidence = round(share * (0.5 + 0.5 * margin), 3)

    if confidence < CONFIDENCE_FLOOR:
        return _fallback(email, best, confidence)

    return best, confidence


def _fallback(email: dict, rule_guess: Category, rule_confidence: float) -> tuple[Category, float]:
    """Ask Gemini when the rules are unsure; degrade to the rule guess."""
    try:
        category = classify_with_gemini(email)
    except Exception:
        return rule_guess, rule_confidence
    if category is None:
        return rule_guess, rule_confidence
    # A model call that agrees with the rules is stronger evidence than
    # either alone; disagreement keeps a deliberately middling confidence.
    return category, 0.75 if category == rule_guess else 0.55


GEMINI_PROMPT = """You are triaging a shipping operations inbox.
Classify the email into exactly one category:

- BL_COMPARISON: asks someone to check/confirm a draft Bill of Lading
  against a Shipping Instruction (usually both are attached).
- SI_REQUEST: asks for a Shipping Instruction to be sent, submitted or created.
- INVOICE_QUERY: about billing, invoices, freight charges, demurrage/detention.
- GENERAL: routine internal notices, reports, reminders, HR/holiday messages.
- SPAM: phishing, prizes, parcel-fee scams, mailbox-full scams.

Respond with only the category name, nothing else.

Subject: {subject}

Body:
{body}
"""


def classify_with_gemini(email: dict) -> Category | None:
    """Single-label classification via Gemini. Returns None if unparseable."""
    from app.config import settings
    from app.gemini_client import get_client

    client = get_client()
    prompt = GEMINI_PROMPT.format(
        subject=_text_of(email, "subject", "title"),
        body=_text_of(email, "body", "text", "content")[:4000],
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
    )
    answer = (getattr(response, "text", "") or "").strip().upper()
    for category in Category:
        if category.value in answer:
            return category
    return None
