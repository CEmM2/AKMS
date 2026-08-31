# State files

Every persistent piece of UI state lives in a JSON file under
`Sources_Evals/NLM/`. All writes are atomic
(`tempfile.mkstemp` + `os.replace`).

## `batch_assignments.json`

Default: `<repo>/Sources_Evals/NLM/batch_assignments.json` — override with
`AKMS_BATCH_STATE`.

Created on first save; absent until then.

### Schema (v1)

```json
{
  "version": 1,
  "updated_at": "2026-05-07T15:48:18Z",
  "batches": {
    "R7_B2": {
      "papers": [
        "wuComprehensiveImplementationsPhasefield2020",
        "wuBFGSMonolithicAlgorithm2020",
        "..."
      ],
      "nlm_notebook_id": "nb_abc123",
      "nlm_notebook_url": "",
      "synced_at": "2026-05-07T19:30:00Z",
      "uploaded_papers": [
        "wuComprehensiveImplementationsPhasefield2020"
      ],
      "notes": ""
    },
    "R7_B3": {
      "papers": [],
      "nlm_notebook_id": "",
      "nlm_notebook_url": "",
      "synced_at": "",
      "uploaded_papers": [],
      "notes": ""
    }
  }
}
```

### Field semantics

| Field | Type | Notes |
|-------|------|-------|
| `version` | int | Always `1` for now. Bump if schema changes. |
| `updated_at` | ISO8601 UTC | Stamped on every save. |
| `batches` | dict | Keyed by batch ID (e.g. `R7_B2`). Sparse — batches you haven't touched aren't here. |
| `batches.*.papers` | list of citekeys | Order is the order you added them. |
| `batches.*.nlm_notebook_id` | string | Populated by `Create NLM notebook`. Empty until then. |
| `batches.*.nlm_notebook_url` | string | Currently unused but reserved. |
| `batches.*.synced_at` | ISO8601 UTC | Stamped on successful `create_notebook`. |
| `batches.*.uploaded_papers` | list of citekeys | Strict subset of `papers`. Used to skip already-uploaded files on rerun. |
| `batches.*.notes` | string | Free-form, written from the UI but currently no UI for editing. |

### Invariants

- `uploaded_papers ⊆ papers` — `papers/remove` and `papers/move` strip the removed citekeys from `uploaded_papers` too.
- `papers` is deduplicated (preserving insertion order).
- All citekeys here ought to exist in the BBT export. If a citekey appears
  in `papers` but is missing from BBT, the UI shows it as an "unknown
  citekey" pill so you can clean it up.

## `saved_queries.json`

Default: `<repo>/Sources_Evals/NLM/saved_queries.json` — override with
`AKMS_SAVED_QUERIES`.

### Schema (v1)

```json
{
  "version": 1,
  "updated_at": "2026-05-07T15:48:18Z",
  "queries": {
    "phase-field-core": {
      "filter": {
        "q": "phase field",
        "collection": ["PFfrac", "Computational"],
        "year_from": 2018,
        "year_to": null,
        "item_type": "",
        "only_with_pdf": true,
        "suggest_for": "R7_B2"
      },
      "created_at": "2026-05-07T15:48:18Z",
      "updated_at": "2026-05-07T15:48:18Z"
    }
  }
}
```

### Field semantics

| Field | Type | Notes |
|-------|------|-------|
| `version` | int | `1` |
| `queries.<name>` | dict | Keyed by user-chosen name. Names are arbitrary strings (URL-encoded by the API). |
| `queries.*.filter` | [`FilterSpec`](../../../architecture/batch-picker.md#filterspec-serverpy) | Same shape as the `/api/papers` query parameters. |
| `queries.*.created_at` / `updated_at` | ISO8601 UTC | First-create vs. last-overwrite. |

`suggest_for` is **persisted** in the saved query — but when you
**Apply** a saved query, the UI sets the toggle based on whether
`suggest_for` is non-empty, and ties the actual scoring to **the currently
selected batch** (not the one stored in the saved query). This way you can
reuse the same "interesting collection of phase-field papers" filter
across multiple batches.

## Per-batch plan JSON — `Sources_Evals/NLM/Inputs/<slug>_plan.json`

Output of **Write plan JSON**. Consumed by `node-gen-invoker`.

### Schema

```json
{
  "plan": "Round 7 — Phase-Field Fracture Methodology",
  "batch_id": "R7_B2",
  "batch_title": "Energy Decomposition & Solution Strategies",
  "round": 7,
  "subdomain": "`phase-field` / `damage-mechanics`",
  "total_nodes": 7,
  "new_nodes": 7,
  "existing_nodes": 0,
  "notes": {
    "source_convention": "Sources picked manually via batch_picker UI; one NLM notebook per batch.",
    "notebook_setup": "Upload 12 PDFs from AKMS_Sources/new/R7_B2_pf_energy_solvers/",
    "round": 7
  },
  "notebook_sources": [
    "Wu et al. (2020) — A comprehensive implementation of the phase-field damage theory ...",
    "..."
  ],
  "papers_by_citekey": [
    {
      "citekey": "wuComprehensiveImplementationsPhasefield2020",
      "label": "Wu et al. (2020) — A comprehensive ...",
      "pdf": "~/wuComprehensive...pdf",
      "has_pdf": true
    },
    "..."
  ],
  "clusters": [
    {
      "cluster": "R7_B2",
      "name": "Energy Decomposition & Solution Strategies",
      "notebook_sources": [...],
      "nodes": [
        {
          "id": "pf-at1-regularization",
          "title": "AT1 regularization",
          "size": "medium",
          "status": "new"
        },
        "..."
      ]
    }
  ],
  "nlm": {
    "notebook_id": "nb_abc123",
    "notebook_url": "",
    "uploaded_papers": ["..."]
  },
  "generated_at": "2026-05-07T15:48:18Z"
}
```

### Why the duplication?

The `notebook_sources` list (free-text labels) is what the existing
`node-gen-invoker` skill expects. The `papers_by_citekey` block is
**additive** — it preserves the explicit citekey ↔ PDF mapping that
motivated this whole tool. New downstream tooling should prefer
`papers_by_citekey`; the legacy list is for backward compatibility.

## Staged PDFs — `AKMS_Sources/new/<slug>/<citekey>.pdf`

Symlinks (default) or copies (if `use_symlink=false` is passed to
`/stage_pdfs`). Filename is the BBT citekey, so duplicates are impossible
and downstream tools can recover the citekey from the filename.

If you re-run **Stage PDFs** after adding/removing papers, existing
symlinks are replaced. Stale symlinks for removed papers are **not**
cleaned up automatically — that's a manual step:

```bash
# Sanity-clean a batch folder by removing symlinks that don't correspond
# to currently assigned citekeys
cd AKMS_Sources/new/R7_B2_pf_energy_solvers/
# (then manual rm of any orphaned <citekey>.pdf entries)
```

A future version may add a `cleanup_pdfs` action; not implemented today.

## Backing up

All four artifact types are plain text JSON or filesystem symlinks. Treat
them like any other repo artifact — commit to git or back up to your
preferred sync system. None of them contain secrets.
