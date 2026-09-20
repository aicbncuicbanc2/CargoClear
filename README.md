# CargoClear — Shipping Document Verification

**Live demo: https://shipdoc-verify-a5povl5zsa-as.a.run.app**

Averis x Monash Hackathon 2026.

Shipping-ops inboxes mix document-check requests in with everything else. For
the emails that *are* document checks, CargoClear compares the **Shipping
Instruction (SI)** against the draft **Bill of Lading (BL)** across 7 fields
and catches mismatches before the draft is finalized — including when the two
documents label the same field differently ("Port of Loading" vs "Load Port"),
which is aligned by meaning rather than by header text.

The pipeline has four stages:

**Classify** → **Extract** → **Compare** → **Ask for help**

The last stage matters as much as the first three: when a comparison can't be
made confidently, the email is escalated to a human review queue with a
reason, rather than guessed at or failed silently.

## What it does

| Stage | File | Approach |
|---|---|---|
| 1. Classify | `app/pipeline/classify.py` | Weighted deterministic signal rules across 5 categories; Gemini is consulted only when rule confidence falls below a floor (~4% of the inbox) |
| 2. Extract | `app/pipeline/extract.py` | Anchored alias matching over `.txt` / `.pdf` / `.docx` / `.xlsx` readers |
| 3. Compare | `app/pipeline/compare.py` | Deterministic diff with value normalization — **not** an LLM, so the verdict is reproducible and explainable |
| 4. Escalate | `app/pipeline/escalate.py` | All 4 review reasons, in precedence order |

Compared fields: `shipper`, `consignee`, `notify_party`, `port_of_loading`,
`port_of_discharge`, `container_count`, `gross_weight_kg`.

### Showing its working

An ops user has to be able to argue with a verdict, not just receive it, so
each screen reports why it said what it said:

- **Stage 1** shows its confidence and the signals it keyed on
  (*"subject says 'draft BL'"*, *"carries both an SI and a BL attachment"*).
- **Stage 2** shows the header each document actually used for a field. This
  is where "align by meaning, not header text" becomes visible: across the
  dataset, **451 field pairs were matched through two different labels** —
  the SI's `Port of Loading` against the BL's `Load Port`, and so on.
- **Stage 3** flags the two cases where a settled verdict still deserves a
  second look: a match that only held *after* normalization (5 in this
  dataset, all thousands separators), and a difference confined to
  punctuation or spacing (none here — every seeded defect in this dataset is
  substantive, and a one-container difference is deliberately *not* softened
  into a near miss just because it moves few characters).

All of this is display-only. It annotates verdicts that are already decided
and cannot move an email between `OK`, `MISMATCH` and `NEEDS_REVIEW` — a
property the test suite asserts directly, because it is what keeps
`submission.json` stable.

A blank or unreadable field is never reported as a mismatch — it becomes
`NEEDS_REVIEW` with `has_defect=false`. Claiming a defect you can't
substantiate is worse than admitting you couldn't read the document.

### Output schema

One JSON object keyed by `email_id`, matching the provided
`sample_submission.json`:

```json
{"email_004": {"category": "BL_COMPARISON", "status": "MISMATCH",
               "review_reason": null, "has_defect": true,
               "defect_fields": ["consignee", "notify_party"]}}
```

- `category`: `BL_COMPARISON` | `SI_REQUEST` | `INVOICE_QUERY` | `GENERAL` | `SPAM`
- `status`: `OK` (all 7 match) | `MISMATCH` (≥1 differs) | `NEEDS_REVIEW` (couldn't compare confidently)
- `review_reason` (set only when `status=NEEDS_REVIEW`): `wrong_doc_type` | `missing_attachment` | `unreadable` | `missing_value`

## Setup

Requires Python 3.12.

```bash
git clone https://github.com/aicbncuicbanc2/CargoClear
cd CargoClear

python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then fill in GEMINI_API_KEY
```

A Gemini key is **optional** for a local run. Without one the Gemini fallback
is skipped and the rule-based classifier decides every email on its own; the
app starts and runs either way.

### Dataset

The participant bundle (`inbox/`, `attachments/`, `loader.py`,
`sample_submission.json`) goes in `data/`, which is gitignored and therefore
not part of this clone — extract it yourself:

```
data/
  inbox/                 520 emails
  attachments/           250 files (.txt, .pdf, .xlsx, .docx)
  loader.py              provided Inbox interface
  sample_submission.json
```

Point `DATASET_SOURCE` at that directory (the default, `data`) or at a running
dataset server (`http://localhost:8080`).

## Running it

```bash
# Test suite — 158 tests
pytest tests -q

# Full pipeline over all 520 emails; writes submission.json (~45s)
python -m app.pipeline.pipeline

# Web UI at http://localhost:8000
uvicorn app.main:app --reload
```

`tests/test_dataset_coverage.py` runs against the real bundle and skips
automatically when `data/` is absent, so the suite passes on a fresh clone.

### Routes

| Route | Purpose |
|---|---|
| `/` | Inbox overview — every email with category, status and attachment count, filterable |
| `/email/{id}` | Per-email comparison: the 7 fields side by side, SI vs BL, with the source excerpt from each document as evidence |
| `/review` | Human review queue — the escalated emails, each tagged with its review reason and evidence |
| `/submission.json` | The graded artifact, downloadable, built from the same cached run the screens render |
| `/health` | Health probe (also `/healthz` locally — see the deploy note) |

The inbox is searchable by email id, subject or sender, and combines with the
category and status filters.

The inbox runs the pipeline once and caches the result in memory, so the first
request is slow and every later one is fast.

## Deploy (Cloud Run)

Run this from **PowerShell, not Git Bash** — Git Bash rewrites
`/app/data` into a Windows path on the way to gcloud, and the container then
can't find the dataset.

```powershell
gcloud run deploy shipdoc-verify --source . `
  --project cargoclear-509012 `
  --region asia-southeast1 `
  --allow-unauthenticated `
  --set-env-vars "GEMINI_API_KEY=<key>,GEMINI_MODEL=gemini-3.6-flash,DATASET_SOURCE=/app/data"
```

Three things are load-bearing and easy to get wrong:

- **`.gcloudignore` must exist and must not exclude `data/`.** Without the
  file, gcloud falls back to `.gitignore` to decide what to upload — and the
  dataset is deliberately gitignored. The build still succeeds and every page
  then 500s. A local `docker build` cannot catch this, because it reads
  `.dockerignore` instead.
- **Probe `/health`, not `/healthz`,** on `*.run.app`. Google's edge
  intercepts that exact path and returns its own 404 before the request ever
  reaches the container.
- **The Gemini model id is configurable on purpose** (`GEMINI_MODEL`). Google
  retires ids on their own schedule — `gemini-2.0-flash` already returns
  `404 no longer available`. The client swallows Gemini errors and keeps the
  rule-based verdict, so an outage costs accuracy on ~4% of emails instead of
  breaking the run.

Local container check:

```bash
docker build -t shipdoc-verify .
docker run -p 8080:8080 -e GEMINI_API_KEY=<key> shipdoc-verify
```

## Project layout

```
app/
  main.py            FastAPI app + routes
  config.py          Settings via pydantic-settings (.env)
  gemini_client.py   Gemini API wrapper
  pipeline/
    models.py        Category/Status/ReviewReason enums, EmailResult
    classify.py      Stage 1
    extract.py       Stage 2
    compare.py       Stage 3
    escalate.py      Stage 4
    pipeline.py      Runner — writes submission.json
    dataset.py       Wraps the provided loader.py Inbox interface
  templates/         Jinja2, Pico.css via CDN
tests/               pytest suite (158 tests)
docs/
  manual-trace-email_004.md   One email traced end-to-end by hand
Dockerfile
```

## Notes on accuracy

Everything below is a structural invariant or a comparison against the
dataset README's own description of itself. **No scoring against ground truth
has been done** — there is no participant-facing self-eval endpoint, and the
organizers' internal kit (which bundles labels in the clear) is deliberately
not used anywhere in this repo.

- Extraction recovers all 7 fields from every non-edge-case document
  (168 txt, 20 pdf, 22 xlsx, 8 docx). The only documents that don't fully
  extract are the 20 purpose-built edge cases, which are meant to fail.
- Classification lands within ~2.3 points of the dataset README's stated
  category distribution on all five categories.
- Escalation produces exactly 20 `NEEDS_REVIEW`, 5 per reason, each in its
  correct group.
- Value normalization prevents 5 false defects (thousands separators, e.g.
  `243588` vs `243,588`).
- `email_004` reproduces `docs/manual-trace-email_004.md` exactly: MISMATCH on
  `consignee` + `notify_party`, the other five fields matching.

Per-category counts vary by ±1 between runs, because the ~4% of emails below
the confidence floor consult Gemini, which isn't deterministic.
