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

520 emails in `data/inbox/` (gitignored — not committed), ~109 SI+BL
attachment pairs in `data/attachments/`: ~78% plain `.txt`, ~22% real binary
(`pdf+pdf`, `xlsx+docx`, `xlsx+xlsx`). `data/loader.py` ships an `Inbox`
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
    classify.py        Stage 1 — NotImplementedError stub, has subject-signal notes
    extract.py          Stage 2 — NotImplementedError stub, FIELD_ALIASES seeded from email_004
    compare.py           Stage 3 — NotImplementedError stub
    escalate.py           Stage 4 — NotImplementedError stub, review_reason triggers documented
    dataset.py           Wraps data/loader.py's Inbox interface
  templates/          Jinja2 (base/inbox/email_detail/review), Pico.css via CDN
docs/
  manual-trace-email_004.md   Worked example
Dockerfile           For Cloud Run deploy
.env.example         Copy to .env, fill in GEMINI_API_KEY
```

## Status as of handoff (Fri 18 Sep, done in a Cowork cloud session)

- [x] Repo scaffolded, FastAPI app boots, all routes smoke-tested (200s)
- [x] Dependencies install cleanly into `.venv` (isolated venv, not system Python)
- [x] Dataset extracted into `data/` (gitignored), `loader.py` present
- [x] Schema aligned exactly to `sample_submission.json` / dataset README
- [x] One email (`email_004`) manually traced end-to-end by hand
- [ ] **git init / commit / push not yet done** — that cloud session had no
      shell on this machine, so files were written here via file transfer
      only. Do this first:
      ```bash
      cd ~/projects/CargoClear
      git init
      git add .
      git commit -m "Scaffold FastAPI app + pipeline structure, align schema with dataset"
      git branch -M main
      git remote add origin https://github.com/aicbncuicbanc2/CargoClear.git
      git push -u origin main
      ```
- [ ] `.env` not created yet — copy `.env.example` to `.env` and fill in `GEMINI_API_KEY`
- [ ] Classify stage (Sat)
- [ ] Extract stage — plain-text alias matching first, Gemini fallback for pdf/docx/xlsx (Sat)
- [ ] Compare stage (Sun)
- [ ] Escalate/review-reason logic (Sun)
- [ ] Run against self-eval endpoint, iterate (Sun)
- [ ] Report UI wired to real pipeline output (Mon)
- [ ] Deploy to Cloud Run, get live URL (Mon)
- [ ] README finalized with setup instructions (Mon)
- [ ] Demo video, slide deck, final smoke test, submit via Google Form (Tue, before noon)

## Day-by-day (from the original build plan)

- **Fri 18 (today)**: repo + dataset + scaffold + manual trace — see Status above.
- **Sat 19**: Classify (all 5 categories) + Extract (7 fields, plain-text +
  alias handling). Workshop 1, 12–1pm.
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
