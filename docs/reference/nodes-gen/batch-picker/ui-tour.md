# UI tour

A reference for every visible control. Open the picker (`akms-pick`) and read
this side-by-side.

## Header

| Element | Behavior |
|---------|----------|
| Brand line | Shows the resolved plan markdown filename and the state file name — quick sanity check that you're hitting the right paths. |
| **↻ Reload data** | Calls `POST /api/reload`. Reloads `zsumbib.json`, the ZotSums vault, the plan markdown, and both state files from disk. Use after editing `generation_plan.md` or refreshing the BBT export. |

## Left pane — batch tree

Batches are grouped by Round (`R1`, `R2`, …) with their round title.

**Per-batch row:**

```
R7_B2                                [synced|partial|ready|empty]
Energy Decomposition & Solution Strategies
12 papers · 7/7 nodes · nb ✓ (12 up)
```

| Status badge | Meaning |
|--------------|---------|
| `empty` (gray) | No papers assigned. |
| `ready` (orange) | Papers assigned, no NLM notebook yet. |
| `partial` (orange) | Notebook created but not all assigned papers uploaded. |
| `synced` (green) | Notebook exists and uploaded count ≥ assigned count. |

Sub-line metrics:

| Metric | Source |
- :material-arrow-right-bold: **Copy-to-batch popover** — click = copy, ++shift++ + click = move; works on assigned-paper pills and on each search-result row.
| `N papers` | `len(assignment.papers)` |
| `K/M nodes` | parsed nodes / declared in plan header (mismatch is highlighted via `M`) |
| `nb ✓ (U up)` | notebook ID present + uploaded count |

**Filter box** — type any substring; matches batch ID, title, or round title.

**Visual cues**

- Active batch — accent left border (blue)
- Compared batch — warn left border (orange) when **Compare with** is set

## Right pane — batch detail

### Header strip

- **Title** — `<batch id> — <title>`
- **Meta line** — round title, parsed/declared node count, PDF folder slug
- **Compare with: [— pick —]** — sets a comparison target (any other batch)
- **Action column** — three buttons (Write plan JSON / Stage PDFs / Create NLM notebook…) — disabled while no papers are assigned

### Batch info & nodes (collapsed by default)

Two-column metadata block:

| Left column (parsed from plan) | Right column (assignment state) |
|--------------------------------|---------------------------------|
| Plan sources hint (free text) | Notebook ID |
| ZotSums hint | Synced timestamp |
| Missing sources hint | Uploaded count |

Followed by the **Nodes** table — every row in the plan's node table, with
ID, title, and size.

### Assigned papers strip

Pills of citekeys currently assigned to this batch.

| Pill state | Color | Meaning |
|------------|-------|---------|
| Default | accent (cyan) | Has a local PDF |
| `no-pdf` | warn (orange) | Citekey is in BBT but no local PDF — extraction will skip it |
| Unknown citekey | warn | Citekey saved in state but not in current BBT export |

**Per-pill buttons:**

- :material-arrow-right: opens the [copy-to-batch popover](#copy-to-batch-popover) for that single paper
- :material-close: removes the paper from this batch

### Compare panel (visible when **Compare with** is set)

Three-column layout:

| Column | Content | Bulk actions |
|--------|---------|--------------|
| **Only in A** (current batch) | Papers unique to the current batch | **Move → B** / **Remove** |
| **In both** | Papers shared between both batches | (read-only) |
| **Only in B** (compared batch) | Papers in the compared batch only | **← Copy** / **← Move** |

Each column has a per-row checkbox plus an **all** checkbox in its action
strip. All bulk operations are atomic — they re-render the panel and the
batch tree once they complete.

### Picker toolbar (row 1 — filters)

| Control | Effect | Notes |
|---------|--------|-------|
| Search box | Substring match in citekey / title / authors / keywords / tags / abstract | Case-insensitive |
| Collections | Multi-select (cmd-click on macOS, ctrl-click elsewhere) | OR'd: a paper matches if it's in any selected collection |
| year ≥ / year ≤ | Inclusive range | Papers without a parseable year are excluded when either bound is set |
| any item type | Filter by Zotero `itemType` | e.g. `journalArticle`, `book`, `report` |
| only with PDF | Default **on** | Drops papers with no local PDF path |
| suggest for this batch | Default off | Computes a score per paper; sorts results by score desc |
| **Search** | Re-runs the query | Auto-triggered on any filter change too |

### Picker toolbar (row 2 — saved queries + bulk add)

| Control | Effect |
|---------|--------|
| Saved query dropdown | Lists queries from `Sources_Evals/NLM/saved_queries.json`. |
| **Apply** | Loads the selected query's filter spec into the toolbar and runs the search. |
| **Save current as…** | Prompts for a name; persists the current toolbar state. Re-using a name overwrites. |
| **Delete** | Removes the selected saved query (with confirm). |
| `search-stats` | "N shown / M match" — capped at `limit=300`; the count is the full server-side total. |
| Bulk-mode dropdown | `Add all matching` (union) or `Replace batch with matching` (drop existing). |
| **→ Apply to batch** | Pushes every match of the current filter into the active batch (with confirm dialog). Disabled if no batch is selected or no results matched. |

### Results table

| Column | Content | Sortable |
|--------|---------|----------|
| ☐ | Checkbox — toggling fires `add` or `remove` immediately | — |
| Citekey | BBT citation key — clickable, opens the [paper modal](#paper-modal) | by citekey alphabetically |
| Title | Truncated at 80 chars; full title in tooltip | — |
| Year | Parsed from `date` | — |
| Authors | First author last-name + " et al." if more than one | — |
| Collections | First 3 collection names | — |
| Keywords | First 4 ZotSums-curated keywords as chips | — |
| PDF | ✓ if a local PDF path exists | — |
| Used in | Other batches that already have this paper | — |
| Score | Suggest score (if `suggest_for` is on) — see [Architecture](../../../architecture/batch-picker.md#suggest-scoring) | sort order |
| → | Opens [copy-to-batch popover](#copy-to-batch-popover) for this row | — |

**Row tinting**

| Tint | Meaning |
|------|---------|
| (none) | Not assigned anywhere |
| Green wash | Already assigned to **the current batch** |
| Orange wash | Assigned to **another batch** but not this one |

## Paper modal

Triggered by clicking a citekey. Shows everything we know about a paper:

- Year · item type · full author list
- Publication, DOI (link), URL (link)
- All collection names
- ZotSums keywords (cyan chips) + Zotero tags (gray chips)
- Abstract
- Problem / Methods / Key Findings / Limitations sections from the ZotSums
  Obsidian note (if available)
- Local PDF absolute path

Click outside the dialog or hit `×` to close.

## Copy-to-batch popover

Triggered by:

- **→** button on an assigned pill
- **→** button on a result-table row

The popover shows every batch (filterable). Click any row:

- :material-cursor-default-click: **Click** — copy the paper(s) into that batch (`papers/add`)
- :material-keyboard-shift: **Shift+click** — move the paper(s) — adds to target, removes from source (`papers/move`)

The source batch (the batch you're currently in, or the one explicitly passed
to the popover) is rendered disabled with a "current" tag — clicking it is a
no-op.

## Toasts

Bottom-right notifications. Color-coded: green = success, orange = warn, red =
error. Errors stay for 8 seconds; everything else auto-dismisses in 3.5.

## Confirm and prompt dialogs

The picker uses native `<dialog>` elements (no third-party modal lib). Hit the
`×` button, the **Cancel** button, click outside the dialog, or press
++escape++ to dismiss.

## Keyboard shortcuts

| Where | Key | Effect |
|-------|-----|--------|
| Search box | ++enter++ | Re-run search |
| Prompt dialog | ++enter++ | Accept |
| Prompt dialog | ++escape++ | Cancel |
| Any dialog | Click outside | Close |
