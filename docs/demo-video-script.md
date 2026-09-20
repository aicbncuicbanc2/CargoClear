# Demo video script

Target: **3 minutes**. Screen recording with voiceover, no face needed.

## Before you hit record

1. **Warm the service.** Open <https://shipdoc-verify-a5povl5zsa-as.a.run.app>
   once and wait for it to finish. The first request runs the whole pipeline
   (~14s); every later one is ~0.2s. Recording a cold start wastes 14 seconds
   and looks broken.
2. Close other tabs, set the browser to full screen, zoom to ~110% so text is
   readable after compression.
3. Have these three tabs ready in order: the live app, the GitHub repo, the
   deck.

---

## Shot 1 — The problem (0:00–0:25)

*On screen: the inbox overview at `/`.*

> "This is a shipping operations inbox — 520 emails. Some are requests to
> check a draft Bill of Lading against its Shipping Instruction. Most are
> not: invoice queries, routine notices, spam. The first job is telling them
> apart."

*Point at the stats header: 520 processed, 220 comparisons, 48 mismatches,
20 escalated.*

## Shot 2 — Classification (0:25–0:50)

*Use the category filter. Select `SPAM`, then `INVOICE_QUERY`, then
`BL_COMPARISON`.*

> "Five categories. 95.8% of the inbox is decided by deterministic rules —
> no API call at all. Only about 4% is uncertain enough to consult a model,
> and if that model is unavailable the rule verdict stands."

## Shot 3 — A real mismatch (0:50–1:40)

*Search `email_004`. Open it. This is the core of the demo — slow down here.*

> "This email asked for a comparison. Seven fields were checked."

*Point at the consignee and notify_party rows, highlighted red.*

> "Two of them disagree. The Shipping Instruction says one consignee, the
> draft Bill of Lading says another — that is a defect worth catching before
> the document is issued."

*Now point at the small grey labels under the values.*

> "Notice these. The Shipping Instruction calls this field 'Port of Loading';
> the Bill of Lading calls it 'Load Port'. They are matched by meaning, not
> by header text. Across the dataset, 451 field pairs matched through two
> different labels."

*Expand the classification panel.*

> "And it shows its working — the confidence, and the signals it keyed on."

## Shot 4 — Knowing when not to answer (1:40–2:20)

*Go to `/review`.*

> "The stage that matters most is the fourth one. Twenty emails could not be
> compared confidently, and none of them is reported as a defect."

*Scroll through, pointing at the four reasons.*

> "Four reasons: the attachment is missing, the file is unreadable, the
> second document is not a Bill of Lading at all — it's a commercial invoice
> — or a required field is blank. A blank field is never a mismatch. Claiming
> a defect you cannot substantiate costs more trust than admitting you
> couldn't read the document."

## Shot 5 — The output (2:20–2:40)

*Click `submission.json` in the nav.*

> "The graded output is served straight from the same run you have been
> looking at — 520 entries, one per email."

## Shot 6 — Close (2:40–3:00)

*Switch to the GitHub repo, scroll the README briefly.*

> "It's a FastAPI app on Cloud Run, 158 tests, and the comparison logic is
> deterministic Python rather than a model call, so every verdict is
> reproducible. One thing I want to be straight about: accuracy hasn't been
> measured against ground truth, because no scoring endpoint was available.
> Every figure I've quoted is a structural property, not an accuracy claim."

---

## Notes

- **Do not skip the closing honesty line.** It is short and it is the
  difference between a judge trusting the rest of your numbers and not.
- If you fluff a take, keep rolling and redo just that shot — editing two
  clips together is faster than re-recording three minutes.
- Upload to YouTube as **Unlisted** (not Private — judges cannot open
  Private).
- Check the link in a private browser window before submitting.
