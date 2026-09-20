# Project description

Text for the submission form. Two lengths — use whichever fits the field.

## Short (about 90 words)

CargoClear triages a shipping operations inbox and checks draft Bills of
Lading against their Shipping Instructions.

It classifies each email into one of five kinds, extracts seven shipment
fields from whichever documents are attached (`.txt`, `.pdf`, `.docx`,
`.xlsx`), and compares the two documents field by field. The same field is
often labelled differently in each document, so fields are aligned by meaning
rather than by header text.

The comparison itself is deterministic Python, not a model, so every verdict
is reproducible and explainable. When a comparison cannot be made
confidently, the email is escalated to a human review queue with a reason
instead of being guessed at.

## Long (about 240 words)

Shipping operations teams receive inboxes where document-check requests sit
alongside invoice queries, routine notices and spam. For the checks, someone
has to compare a draft Bill of Lading against the Shipping Instruction it was
built from and catch discrepancies before the draft is finalized — a
mismatched consignee or a stale port code is expensive once the document is
issued.

CargoClear automates that check in four stages.

**Classify** sorts each email into `BL_COMPARISON`, `SI_REQUEST`,
`INVOICE_QUERY`, `GENERAL` or `SPAM`, using weighted signal rules that decide
95.8% of the inbox on their own. Only the uncertain remainder consults
Gemini, and if the API is unavailable the rule verdict stands, so an outage
degrades accuracy rather than breaking the run.

**Extract** pulls seven fields from each attached document across four file
formats. Because the SI and the BL are produced by different systems, the
same field carries a different header in each — across this dataset, 451
field pairs were matched through two different labels.

**Compare** is a deterministic diff, deliberately not a model call. It
normalizes formatting differences that are not defects while preserving the
ones that are.

**Ask for help** escalates anything that cannot be judged confidently, with
one of four reasons. A blank or unreadable field is never reported as a
mismatch.

A web report shows the inbox, each comparison with the evidence behind it,
and the review queue.

**Note on validation:** accuracy has not been measured against ground truth,
as no participant scoring endpoint was available.
