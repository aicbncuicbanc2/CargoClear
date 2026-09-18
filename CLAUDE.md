# CargoClear — Shipping Document Verification

Averis x Monash Hackathon 2026. Solo build. Submission deadline: **22 Sep
2026, 12:00 p.m.** Finals (if shortlisted): 26 Sep at Monash Malaysia,
Subang Jaya — must be physically present.

This file is a handoff written by a prior Cowork (cloud) session so a fresh
Claude Code session in this folder has full context immediately.

## Problem

Shipping ops inbox mixes document-check requests with other message types.
For a document-comparison email, compare the **Shipping Instruction (SI)**
against the draft **Bill of Lading (BL)** across 7 fields and catch
mismatches before the draft is finalized. Same field can have different
labels across documents (e.g. "Port of Loading" vs "Load Port") — must
align by meaning, not header text.

Pipeline stages (per the official capability table): **Classify** → **Extract**
→ **Compare** → **Ask for help** (escalate to human review rather than
guess/fail silently).

## Exact required output schema (confirmed against the real dataset)

One JSON object keyed by `email_id`, matching `data/sample_submission.json`:

```json
{"email_004": {"category": "BL_COMPARISON", "status": "MISMATCH",
               "review_reason": null, "has_defect": true,
               "defect_fields": ["consignee", "notify_party"]}}
```

- `category`: `BL_COMPARISON` | `SI_REQUEST` | `INVOICE_QUERY` | `GENERAL` | `SPAM`
- `status`: `OK` (all 7 match) | `MISMATCH` (>=1 differs) | `NEEDS_REVIEW` (couldn't compare confidently)
- `review_reason` (only when `status=NEEDS_REVIEW`): `wrong_doc_type` | `missing_attachment` | `unreadable` | `missing_value`
- A blank/unreadable field is **never** a mismatch — it's `NEEDS_REVIEW`, `has_defect=False`.
- The 7 compared fields: `shipper, consignee, notify_party, port_of_loading, port_of_discharge, container_count, gross_weight_kg`

These exact enum values are already encoded in `app/pipeline/models.py`
(`Category`, `Status`, `ReviewReason`, `EmailResult.to_submission()`).

## Dataset

520 emails in `data/inbox/` (gitignored — not committed) and 250 files in
`data/attachments/`. Measured: 126 emails carry attachments, 124 of them a
2-file SI+BL pair. By pair shape: 94 `txt+txt`, 13 `pdf+pdf`, 8
`xlsx+docx`, 7 `xlsx+xlsx`, 2 `txt+pdf`, 2 SI-only. By file: 192 `.txt`,
28 `.pdf`, 22 `.xlsx`, 8 `.docx`. `data/loader.py` ships an `Inbox`
class — see its docstring for the local-file vs HTTP-server interface.
`docs/manual-trace-email_004.md` is a hand-worked example (real mismatch on
`consignee` + `notify_party`, with the label synonyms observed).

Category mix (~500 main + 20 edge cases): `BL_COMPARISON` ~40%, `SI_REQUEST`
~25%, `INVOICE_QUERY` ~15%, `GENERAL` ~12%, `SPAM` ~8%. Edge cases
(`email_501`-`email_520`) are all `BL_COMPARISON` that should resolve to
`NEEDS_REVIEW`, 5 per `review_reason`.

### ⚠️ Do not use the "docker" zip's ground truth

You (the user) were also given `sdoc-hackathon-docker.zip` — that is the
**organizers'** internal kit, not a participant deliverable. Its own README
says "Do NOT hand it to participants" and it bundles `ground_truth.json` in
the clear. It was NOT extracted or committed anywhere in this repo, and its
labels must never be read into the pipeline logic — that would be an
integrity violation, not a shortcut. If a local self-eval loop is wanted,
use the participant-facing `/submit` endpoint or `score_cli.py` as intended,
never the raw ground truth file. If you (Claude Code) ever see a
`ground_truth.json` path anywhere in this working tree, stop and flag it —
it should not be there.

## Stack

- **AI**: Gemini API (Google AI Studio, free tier) — user already has a key
- **Cloud**: GCP Cloud Run, project `cargoclear-509012` (free trial billing
  account, shared with an unrelated "Thyme" project — same credit pool)
- **Backend**: Python + FastAPI, server-rendered Jinja2 UI (no separate
  frontend build)
- **Compare logic**: deterministic Python diff, not LLM, once fields are
  extracted

## Repo layout

```
app/
  main.py            FastAPI app + routes (/  /email/{id}  /review  /healthz)
  config.py          Settings via pydantic-settings (.env)
  gemini_client.py   Gemini API client wrapper (needs GEMINI_API_KEY)
  pipeline/
    models.py         Category/Status/ReviewReason enums + EmailResult (submission shape)
    classify.py        Stage 1 — DONE. Weighted signal rules + Gemini fallback
    extract.py          Stage 2 — DONE. Alias matching + txt/pdf/docx/xlsx readers
    compare.py           Stage 3 — NotImplementedError stub
    escalate.py           Stage 4 — NotImplementedError stub, review_reason triggers documented
    dataset.py           Wraps data/loader.py's Inbox interface
  templates/          Jinja2 (base/inbox/email_detail/review), Pico.css via CDN
tests/              pytest suite (69 tests); test_dataset_coverage.py runs
                    against the real bundle and skips when data/ is absent
docs/
  manual-trace-email_004.md   Worked example
Dockerfile           For Cloud Run deploy
.env.example         Copy to .env, fill in GEMINI_API_KEY
```

## Status as of Fri 18 Sep (verified in a Claude Code session on this machine)

The previous handoff's status list was written by a cloud session that had
no shell here, and three of its checkmarks did not hold on this machine:
`.venv` did not exist, `data/` held nothing but `.gitkeep`, and the repo was
not a git repo at all. Everything below was checked by running it.

- [x] Repo scaffolded, FastAPI app boots, all 4 routes smoke-tested (200s)
- [x] `.venv` created here and dependencies installed (isolated venv, not
      system Python). Recreate with:
      `python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt`
- [x] Dataset extracted into `data/` (gitignored): 520 emails, 250
      attachment files, `loader.py`, `sample_submission.json`, README
- [x] Schema aligned exactly to `sample_submission.json` / dataset README
- [x] One email (`email_004`) manually traced end-to-end by hand
- [x] git init / commit / push **done** — remote already had GitHub's
      auto-created "Initial commit" with a stub README, so the scaffold was
      rebased onto it rather than force-pushed. `main` tracks
      `origin/main` at https://github.com/aicbncuicbanc2/CargoClear
- [x] `.env` created from `.env.example` and confirmed gitignored —
      **`GEMINI_API_KEY` is still blank, the user fills it in**
- [x] Classify stage (Sat) — deterministic weighted signals + Gemini
      fallback below `CONFIDENCE_FLOOR`
- [x] Extract stage (Sat) — anchored alias matching over txt/pdf/docx/xlsx
- [ ] Compare stage (Sun)
- [ ] Escalate/review-reason logic (Sun)
- [ ] Run against self-eval endpoint, iterate (Sun)
- [ ] Report UI wired to real pipeline output (Mon) — `app/main.py` still
      renders empty placeholder context, not pipeline output
- [ ] Deploy to Cloud Run, get live URL (Mon)
- [ ] README finalized with setup instructions (Mon)
- [ ] Demo video, slide deck, final smoke test, submit via Google Form (Tue, before noon)

### Measured state of stages 1-2 (against the real dataset, not fixtures)

- Extraction: all 7 fields recovered from **every** non-edge-case document
  (168 txt, 20 pdf, 22 xlsx, 8 docx). The only documents that do not fully
  extract are the 20 purpose-built edge cases, which are *meant* to fail.
- 64 of 119 comparable SI/BL pairs agree on all 7 fields; the rest differ on
  1-3 fields, which is the shape real seeded defects should have.
- Classification: category mix lands within ~2.3 points of the README's
  stated distribution on all five categories, and 96% of the inbox is
  decided by rules alone — only ~4% falls below `CONFIDENCE_FLOOR` and
  would consult Gemini.
- `pytest tests -q` = 69 passing. `tests/test_dataset_coverage.py` asserts
  the figures above and auto-skips when `data/` is absent.

### Environment gotcha specific to this machine

`python-docx` **cannot be imported here** — Application Control policy
blocks lxml's compiled `_elementpath` DLL. The `.docx` reader therefore uses
only the standard library (a .docx is a zip of XML). Do not "fix" this by
reintroducing python-docx; it would work on Cloud Run but break every local
test run.

### Things stage 3/4 will need to handle (found while building stage 2)

- `extract_fields` returns `None` both for a field whose label is absent and
  for one that is present but blank. If `missing_value` needs to be told
  apart from the other review reasons, that distinction has to be recovered
  in stage 4 or surfaced from stage 2.
- Values are **not** normalized: `243588` vs `243,588` and
  `MOMBASA, KENYA (KEMBA)` vs `MOMBASA, KENYA` are formatting differences,
  not defects. Numeric/whitespace/punctuation normalization belongs in
  `compare.py`, or it will manufacture false mismatches.
- The edge-case groups are contiguous and identifiable: 501-505
  wrong_doc_type (BL is a Commercial Invoice etc.), 506-510
  missing_attachment (0 or 1 attachment), 511-515 unreadable (scanned or
  truncated PDFs), 516-520 missing_value (`N/A`, `TBA`, blank).
- `Seller:` / `Buyer:` are deliberately **not** aliased to shipper/consignee.
  Aliasing them would populate fields from the Commercial Invoices in
  501-505 and make `wrong_doc_type` undetectable.

## Day-by-day (from the original build plan)

- **Fri 18**: repo + dataset + scaffold + manual trace — done, see Status above.
- **Sat 19**: Classify (all 5 categories) + Extract (7 fields, plain-text +
  alias handling) — done early, on Fri 18. Workshop 1, 12–1pm.
- **Sun 20**: Compare (deterministic diff) + submission JSON output +
  escalation logic. Run against self-eval, iterate on accuracy.
- **Mon 21**: Report UI (inbox overview / comparison view / review queue),
  deploy to Cloud Run, live URL, README. Workshop 2 (Averis), 7–8pm.
- **Tue 22 (morning)**: demo video, slide deck/docs, final smoke test, submit.

Priority: get classify → extract → compare → escalate solid end-to-end with
a live deployed URL first (covers most of the 70% technical weight) before
attempting stretch goals (scanned docs / OCR, messier inputs beyond what's
already in the dataset).

## Submission checklist (all mandatory)

Project description; demo video (public/unlisted YouTube); slide deck or
docs link (anyone-with-link); GitHub repo with README + setup
instructions; live deployed prototype link, functional during judging.
