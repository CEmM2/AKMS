# Tutorial: populate one batch end-to-end

This walks through the canonical flow: pick papers for **R7_B2 — Energy
Decomposition & Solution Strategies**, push them into a NotebookLM notebook,
and produce a plan JSON for the extraction pipeline.

!!! tip "Follow along live"
    Open `akms-pick`, then keep this page side-by-side. Each step maps to a
    concrete UI action.

## 0. Boot the picker

```bash
akms-pick
```

You should land on the empty right pane with the batch tree on the left.

## 1. Select the batch

Click `R7_B2` in the left pane.

The right pane now shows:

- Header with the batch ID, title, round, and node count
- An expandable **Batch info & nodes** section listing the 7 nodes the
  batch is supposed to produce
- An empty **Assigned papers** strip
- A search toolbar
- An empty results table

## 2. Get a smart shortlist

Tick **suggest for this batch** in the search toolbar, then click **Search**
(or hit ++enter++ in the search box).

The Score column lights up. Top hits are papers whose title / keywords /
tags / abstract share the most distinctive tokens with the batch's title +
node titles + plan hint. For R7_B2 you'll typically see Wu's comprehensive
phase-field implementations and the BFGS monolithic algorithm paper at the
top.

!!! note "How the score is computed"
    Pure deterministic keyword overlap — no LLM, no embeddings.
    See [Architecture › Suggest scoring](../../architecture/batch-picker.md#suggest-scoring)
    for the full algorithm.

## 3. Narrow with collection filters

Cmd-click in the **Collections** picker to multi-select. For R7_B2 you'll
probably want `PFfrac` and `Computational`. The list re-runs on change.

Other handy filters:

- **year ≥** `2018` — drop older surveys
- **only with PDF** — already on by default; flip off only if you want to
  audit citekeys you'll have to retrieve manually

## 4. Assign papers

Tick the checkbox in the leftmost column of each paper you want. Each tick
fires `POST /api/batches/R7_B2/papers/add` and refreshes the assigned-pills
strip at the top.

The row tints:

- :material-check: green tint = already assigned to **this** batch
- :material-alert: orange tint = assigned to **another** batch (cross-batch
  reuse — usually fine for foundational papers)

## 5. (Optional) Bulk-add from a query

Need to grab everything in `PFfrac` newer than 2020? Set those filters,
choose **Add all matching** in the bulk-mode dropdown, then click
**→ Apply to batch**. A confirm dialog shows the match count before
committing.

Pick **Replace batch with matching** instead if you want a clean slate
based purely on the current filter.

## 6. (Optional) Save the query for next time

Hit **Save current as…**, name it (e.g. `pf-monolithic-2020+`), confirm.
The named filter now lives in `Sources_Evals/NLM/saved_queries.json` and
appears in the **Saved query** dropdown across sessions.

## 7. (Optional) Compare with a sibling batch

Pick another batch in the **Compare with** dropdown — say `R7_B1` (the
variational foundations batch). A three-column panel appears below the
assigned-pills:

| Column | What it lists | Useful action |
|--------|---------------|---------------|
| **Only in R7_B2** | Papers unique to the current batch | Move → R7_B1 if they fit better there |
| **In both** | Papers shared between the two | Audit overlap; remove from one if redundant |
| **Only in R7_B1** | Papers in the compared batch but not here | ← Copy to add them; ← Move to take ownership |

Use the per-column **all** checkbox + a bulk button (Move, Copy, Remove) to
shift work between batches.

## 8. Stage PDFs

Click **Stage PDFs**. The picker symlinks each assigned paper's local PDF
into `AKMS_Sources/new/R7_B2_pf_energy_solvers/<citekey>.pdf` so the
extraction pipeline (and your manual inspection) can find them in one
place.

A toast reports `staged N`. If any are skipped, expand the toast — usually
the cause is a missing or moved local file.

## 9. Write the plan JSON

Click **Write plan JSON**. The output lands at
`Sources_Evals/NLM/Inputs/R7_B2_pf_energy_solvers_plan.json` and is wired
into the existing `node-gen-invoker` schema (with extra `papers_by_citekey`
and `nlm` blocks for traceability).

## 10. Create the NLM notebook + upload

Click **Create NLM notebook…**, confirm the dialog. The picker:

1. Calls `nlm notebook create "AKMS R7_B2 — Energy Decomposition & Solution Strategies"`
2. Captures the notebook ID into `batch_assignments.json`
3. Calls `nlm source add <id> --file <pdf> --title "<author> et al. (year) — <title>"`
   for each assigned paper
4. Records each successful upload in `uploaded_papers`

If you re-click the button after adding more papers, only the **delta** is
uploaded — already-uploaded citekeys are skipped.

## 11. Hand off to the extraction pipeline

The plan JSON is now consumable by `node-gen-invoker`:

```bash
/node-gen-invoker <NLM_ID> all \
    Sources_Evals/NLM/Inputs/R7_B2_pf_energy_solvers_plan.json \
    Sources_Evals/NLM/Outputs/R7_B2_pf_energy_solvers/ \
    true
```

(The exact command lives in the AKMS repo's `node-gen` skill — see
[Pipeline integration](../../reference/nodes-gen/batch-picker/pipeline-integration.md) for how
the picker's output maps onto it.)

---

You now have one batch fully curated, uploaded, and ready for extraction.
Repeat for the remaining 29 — or start mass-prepping with the bulk-add /
compare / saved-query features.
