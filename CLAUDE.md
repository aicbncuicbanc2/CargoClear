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
    compare.py           Stage 3 — DONE. Normalizing deterministic diff
    escalate.py           Stage 4 — DONE. All 4 review_reason triggers
    pipeline.py          Runner: classify -> extract -> compare -> escalate
    dataset.py           Wraps data/loader.py's Inbox interface
  templates/          Jinja2 (base/inbox/email_detail/review), Pico.css via CDN
                      base.html owns the badge palette: green=match,
                      red=mismatch, amber=needs review, gray=not a comparison
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
- [x] Compare stage (Sun) — deterministic diff with value normalization
- [x] Escalate/review-reason logic (Sun) — all 4 reasons
- [x] End-to-end runner: `python -m app.pipeline.pipeline` writes
      `submission.json` for all 520 emails (gitignored — it is generated)
- [ ] Run against self-eval endpoint, iterate (Sun) — **blocked**: no
      legitimate scoring endpoint yet. Do not score against any
      ground-truth-derived source; see the integrity note above.
- [x] Report UI wired to real pipeline output (Mon) — all three screens
      render live pipeline results, with category/status filters and an
      in-memory cache (`app/main._REPORTS`) so the inbox runs once, not
      per request
- [x] Gemini key verified live (see the model-id note below)
- [x] Dockerfile fixed and verified by simulating the container layout
- [x] Deployed to Cloud Run. **Live URL:
      https://shipdoc-verify-a5povl5zsa-as.a.run.app**
      (Cloud Run also answers on the longer form
      `https://shipdoc-verify-142988436999.asia-southeast1.run.app`.)
      Project `cargoclear-509012`, region `asia-southeast1`, service
      `shipdoc-verify`, public (`--allow-unauthenticated`).
      Latest revision `shipdoc-verify-00005-m4w`, deployed Sun 20 Sep with
      the explainability work below.
- [x] Explainability pass (Sun 20): classifier confidence + the signals it
      fired on, the header each document used per field, borderline
      annotations, `/submission.json`, and inbox search. All display-only —
      verified byte-identical submission output before and after.
- [x] README finalized with setup instructions (Sun 20, early)
- [ ] Demo video, slide deck, final smoke test, submit via Google Form (Tue, before noon)

### Measured state of the pipeline (against the real dataset, not fixtures)

- Extraction: all 7 fields recovered from **every** non-edge-case document
  (168 txt, 20 pdf, 22 xlsx, 8 docx). The only documents that do not fully
  extract are the 20 purpose-built edge cases, which are *meant* to fail.
- Classification: category mix lands within ~2.3 points of the README's
  stated distribution on all five categories, and 96% of the inbox is
  decided by rules alone — only ~4% falls below `CONFIDENCE_FLOOR` and
  would consult Gemini.
- Full run over 520 emails:
  `BL_COMPARISON` 48 MISMATCH / 152 OK / 20 NEEDS_REVIEW, and
  `SI_REQUEST` 132, `INVOICE_QUERY` 78, `GENERAL` 53, `SPAM` 37 (all OK).
- Escalation: exactly 20 NEEDS_REVIEW, all inside email_501-520, exactly 5
  per review_reason, each landing in its correct group.
- `email_004` reproduces the hand trace exactly: MISMATCH on
  `consignee` + `notify_party`.
- Value normalization prevents 5 real false defects (all thousands
  separators, e.g. `243588` vs `243,588`).
- `pytest tests -q` = 158 passing. `tests/test_dataset_coverage.py` asserts
  the figures above and auto-skips when `data/` is absent.

**No scoring has been attempted.** There is no legitimate self-eval endpoint
yet, and the organizers' `ground_truth.json` must never be used. Every
figure above is either a structural invariant or a comparison against the
dataset README's own description — never against withheld labels.

### Judgment call worth revisiting: BL_COMPARISON emails with no documents

94 emails classify as `BL_COMPARISON` but carry no attachments. 91 of them
read "Please assist to send the draft BL ... for checking" — they are
*requesting* a draft, not failing a comparison, and they are reported
`status=OK` with no review reason, on the grounds that no comparison was
ever attempted. The other 3 (email_506/508/510) read "Please compare the SI
and draft BL ... (attachments appear to have been dropped)" and *are*
`missing_attachment`.

Treating all 94 as `missing_attachment` instead would put 96 emails in the
review queue where the dataset README implies 5. That is the reasoning, but
it is an inference from the README's "5 per review_reason" framing, not a
verified fact — if a scoring endpoint ever becomes available, this is the
first thing to check.

### Gemini model ids move — do not hardcode

`gemini-2.0-flash` was hardcoded in classify.py and now returns
`404 ... is no longer available`. The working id as of 18 Sep is
**`gemini-3.6-flash`**, and it is configurable via `GEMINI_MODEL` in `.env`
rather than baked into the code. The API also returns intermittent
`503 UNAVAILABLE` under load; `_fallback` swallows any exception and keeps
the rule verdict, so a Gemini outage degrades accuracy on ~4% of emails
rather than breaking the run.

### Deploy: what was verified without Docker

Docker is **not installed on this machine**, so `docker build` could not be
dry-run. Instead the container layout was simulated by copying exactly what
the Dockerfile COPYs into a scratch dir and running uvicorn there with
`DATASET_SOURCE`/`PORT`/`GEMINI_API_KEY` supplied as environment variables
and no `.env` file. All three screens served correctly that way.

That simulation caught a real deploy blocker: the original Dockerfile copied
only `app/`, never `data/`. Because `data/` is gitignored it would not have
been in the build context by habit either. The failure mode was nasty —
`/healthz` returns 200 while every real page 500s with
`ModuleNotFoundError: No module named 'loader'` — so Cloud Run would have
reported a healthy deployment of a completely broken app. The Dockerfile now
copies `data/`, sets `DATASET_SOURCE=/app/data`, runs as a non-root user,
and leaves `GEMINI_API_KEY` unset so the secret is supplied at run time. A
`.dockerignore` keeps `.env` and `.venv` out of the image.

**Now verified, by Cloud Build rather than locally:** the 20 Sep deploy
built this exact Dockerfile from source, so the pip install on
`python:3.12-slim` and the non-root `USER` switch both work. Docker is still
not installed here, so the local dry-run below has never been run — but it is
no longer the only evidence that the image is sound.

    docker build -t shipdoc-verify .
    docker run -p 8080:8080 -e GEMINI_API_KEY=... shipdoc-verify

### Deploying again — four traps, all of them hit on the first attempt

Redeploy with (from **PowerShell**, not Git Bash — see trap 2):

    gcloud run deploy shipdoc-verify --source . --project cargoclear-509012       --region asia-southeast1 --allow-unauthenticated       --set-env-vars "GEMINI_API_KEY=<key>,GEMINI_MODEL=gemini-3.6-flash,DATASET_SOURCE=/app/data"

1. **Cloud Build's service account starts with no permissions.** The first
   deploy died with `PERMISSION_DENIED ... could not resolve source`. Projects
   created after Google's 2024 change no longer grant the default compute SA
   the Editor role, so Cloud Build cannot read its own uploaded source. Fixed
   once, permanently, by granting
   `roles/cloudbuild.builds.builder` to
   `142988436999-compute@developer.gserviceaccount.com`.

2. **Git Bash silently rewrites POSIX paths in gcloud arguments.**
   `DATASET_SOURCE=/app/data` arrived in the container as
   `C:/Program Files/Git/app/data` (MSYS2 path mangling). That is not
   absolute on Linux, so it resolved under the repo root, the dataset was
   never found, and every page 500'd with `ModuleNotFoundError: No module
   named 'loader'` — the *same symptom* as trap 3 but a completely different
   cause, which made it easy to misdiagnose. Run gcloud from PowerShell, or
   set `MSYS_NO_PATHCONV=1`.

3. **`.gcloudignore` must exist, and must not exclude `data/`.** Without it
   gcloud falls back to `.gitignore` to decide what to upload — and the
   dataset is deliberately gitignored. The build still succeeds (`COPY data
   ./data` copies a directory holding only `.gitkeep`) and the service then
   500s on every page. A local `docker build` cannot catch this: it reads
   `.dockerignore`, which has no reason to exclude `data/`.

4. **`/healthz` does not work on `*.run.app`.** Google's edge intercepts that
   exact path: it returns a Google HTML 404 with no `server: Google Frontend`
   and no `x-cloud-trace-context` header, and the request never appears in
   Cloud Run's request logs. An unknown path like `/nope` correctly returns
   FastAPI's JSON 404, so this is specific to `/healthz`. The app therefore
   serves the same handler at **`/health`**, which is the path to probe in
   production. `/healthz` is kept for local runs and other hosts.

### Verified live after deploy

Re-verified after the 20 Sep deploy: `/health` 200, `/` 200, `/review` 200,
`/email/email_004` 200, `/submission.json` 200 returning all 520 entries and
matching the locally generated `submission.json` exactly. Search and the
confidence panel render live. Earlier deploy notes:

`/health` 200, `/` 200, `/review` 200, `/email/email_004` 200. Stats header
reads 520 / 220 / 48 / 20, the review queue holds 20 entries at 5 per reason,
and email_004 renders the hand trace exactly — MISMATCH on consignee +
notify_party with the other five fields matching. Cold start (first request,
which runs the whole pipeline) ~14s; every later request ~0.2-0.6s from the
in-memory cache.

### Environment gotcha specific to this machine

`python-docx` **cannot be imported here** — Application Control policy
blocks lxml's compiled `_elementpath` DLL. The `.docx` reader therefore uses
only the standard library (a .docx is a zip of XML). Do not "fix" this by
reintroducing python-docx; it would work on Cloud Run but break every local
test run.

### Design notes carried by stages 2-4

- `extract_fields` is **tri-state**: a key is absent when the label does not
  appear, `""` when the label appears but the value is blank, and a string
  otherwise. `missing_value` depends on that distinction — use
  `is_present` / `is_blank` / `is_usable`, never a truth test on the value.
- `compare.py` normalizes whitespace, case, and thousands separators before
  diffing, and deliberately does **not** strip parenthetical port codes:
  "MOMBASA, KENYA (KEMBA)" vs "TUTICORIN, INDIA (KEMBA)" is a real seeded
  defect where the stale code was left behind.
- Escalation precedence is `missing_attachment -> unreadable ->
  wrong_doc_type -> missing_value`, which is the order in which each check
  becomes possible: a document's type cannot be judged before it can be
  read, and its values cannot be judged before its type is known.
- The edge-case groups are contiguous: 501-505 wrong_doc_type (BL is a
  Commercial Invoice, Packing List or Certificate of Origin), 506-510
  missing_attachment, 511-515 unreadable (scanned or truncated PDFs),
  516-520 missing_value (`N/A`, `TBA`, blank).
- `Seller:` / `Buyer:` are deliberately **not** aliased to shipper/consignee.
  Aliasing them would populate fields from the Commercial Invoices in
  501-505 and make `wrong_doc_type` undetectable.
- 10 SI documents are headed "BILL OF LADING INSTRUCTION". The BL sniffer
  excludes that phrase explicitly, or every SI would look like a BL.

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
