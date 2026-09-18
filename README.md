# Shipping Document Verification

Averis x Monash Hackathon 2026 — classifies shipping-ops inbox emails and
compares Shipping Instruction (SI) vs draft Bill of Lading (BL) documents
across 7 fields, flagging mismatches and escalating uncertain cases for
human review.

## Stack

- **AI**: Gemini API (Google AI Studio, free tier)
- **Cloud**: GCP Cloud Run
- **Backend**: Python + FastAPI, server-rendered Jinja2 UI (no separate frontend)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY
```

### Dataset

The participant static bundle (`inbox/`, `attachments/`,
`sample_submission.json`, `loader.py`) is extracted into `data/` (gitignored
— not committed). 520 emails, ~109 SI+BL attachment pairs (mostly `.txt`,
~22% real `pdf`/`docx`/`xlsx`). See `docs/manual-trace-email_004.md` for a
worked example.

Required submission shape, one entry per `email_id`:

```json
{"email_001": {"category": "BL_COMPARISON", "status": "MISMATCH",
               "review_reason": null, "has_defect": true,
               "defect_fields": ["consignee"]}}
```

`category`: `BL_COMPARISON` | `SI_REQUEST` | `INVOICE_QUERY` | `GENERAL` | `SPAM`
`status`: `OK` | `MISMATCH` | `NEEDS_REVIEW`
`review_reason` (only set when `status=NEEDS_REVIEW`): `wrong_doc_type` |
`missing_attachment` | `unreadable` | `missing_value`

Self-eval: point `DATASET_SOURCE` at a running local dataset server
(`http://localhost:8080`) and call `inbox.submit(...)`, or use `score_cli.py`
if you have it. **Do not commit any `ground_truth.json` or the organizer
docker bundle to this repo** — only the participant bundle's contents belong
here (and even those stay in the gitignored `data/`, never committed).

### Run locally

```bash
uvicorn app.main:app --reload
```

Visit http://localhost:8000

## Project layout

```
app/
  main.py            FastAPI app + routes (inbox, email detail, review queue)
  config.py          Settings (env vars)
  gemini_client.py   Gemini API client wrapper
  pipeline/
    models.py        Shared data shapes (Category, EmailResult, etc.)
    classify.py       Stage 1: classify email into 5 categories
    extract.py         Stage 2: extract 7 shipment fields from SI/BL text
    compare.py          Stage 3: deterministic SI vs BL diff
    escalate.py          Stage 4: human-review escalation logic
    dataset.py          Wrapper around the provided loader.py Inbox interface
  templates/          Jinja2 templates for the report UI
docs/
  manual-trace-email_004.md   Worked example: one email traced by hand end-to-end
```

## Status

Scaffold stage (18 Sep): app boots, routes return 200, dataset wired in,
one email manually traced end-to-end. Pipeline logic (classify/extract/
compare/escalate) and UI are being built out per the day-by-day plan — see
the project's build-plan doc.

## Deploy (Cloud Run)

```bash
gcloud run deploy shipdoc-verify \
  --source . \
  --region <your-region> \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=<key>
```
