# Manual trace: email_004

Fri 18 Sep build-plan step: trace one email + its SI/BL attachments by hand
through the whole pipeline before automating anything.

## Input

- **Email**: `email_004`, from `docs@vitalsolutions.sg`, subject
  `REQUEST BL DRAFT _ PO 26067_ COATED IVORY BOARD__138MT`
- **Attachments**: `email_004_SI.txt`, `email_004_BL.txt` (plain text — the
  simple ~78% case, not one of the pdf/docx/xlsx pairs)

## Stage 1 — Classify

Subject matches the `BL_COMPARISON` signal pattern (`REQUEST BL DRAFT`) and
the body asks to "check the details and confirm" against an attached SI +
draft BL → **category = `BL_COMPARISON`**.

## Stage 2 — Extract

| field | SI label : value | BL label : value |
|---|---|---|
| shipper | `Shipper` : APRIL FAR EAST (M) SDN BHD | `SHIPPER` : APRIL FAR EAST (M) SDN BHD |
| consignee | `Consignee (Non-Negotiable)` : EAST BRIGHT FZ-LLC | `To the Order of` : UAB NOVAKOPA |
| notify_party | `Notify` : EAST BRIGHT FZ-LLC | `Notify Party` : UAB NOVAKOPA |
| port_of_loading | `Port of Loading (POL)` : NANTONG, CHINA (CNNTG) | `Port of Loading (POL)` : NANTONG, CHINA (CNNTG) |
| port_of_discharge | `POD` : KARACHI, PAKISTAN (PKKHI) | `POD` : KARACHI, PAKISTAN (PKKHI) |
| container_count | `Total Containers` : 6 x 40'HC | `Container Count` : 6 x 40'HC |
| gross_weight_kg | `Gross Wt (kgs)` : 131,058 KG | `Gross Weight (KG)` : 131,058 KG |

Confirms the label-synonymy challenge is real even within one email: SI and
BL use different headers for `consignee`, `notify_party`, `container_count`,
and `gross_weight_kg`. These synonyms are now seeded into
`app/pipeline/extract.py`'s `FIELD_ALIASES`.

## Stage 3 — Compare

- shipper: match
- consignee: **mismatch** (EAST BRIGHT FZ-LLC vs UAB NOVAKOPA)
- notify_party: **mismatch** (EAST BRIGHT FZ-LLC vs UAB NOVAKOPA)
- port_of_loading: match
- port_of_discharge: match
- container_count: match
- gross_weight_kg: match

## Stage 4 — Escalate

Both documents parsed cleanly, no missing/blank fields → no escalation
needed. This is a confident `MISMATCH`, not a `NEEDS_REVIEW`.

## Result (submission shape)

```json
{
  "email_004": {
    "category": "BL_COMPARISON",
    "status": "MISMATCH",
    "review_reason": null,
    "has_defect": true,
    "defect_fields": ["consignee", "notify_party"]
  }
}
```

## Takeaways for automation

1. Alias matching needs to be per-field, not global — the same document pair
   can use the seller's own label style for some fields and a different
   convention for others.
2. `consignee` and `notify_party` often move together in real defects (both
   changed here) — worth checking during compare whether observed defects
   cluster, in case that's an intentional generator pattern rather than
   independent per-field noise.
3. Plain-text `.txt` pairs are label:value lines — a regex/line-prefix match
   against `FIELD_ALIASES` should cover most of them without needing Gemini,
   keeping LLM calls for the ambiguous/binary-format cases (pdf/docx/xlsx,
   ~22% of pairs) as the build plan intended.
