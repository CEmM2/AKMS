# HTTP API reference

The picker is a regular FastAPI app — every endpoint is also documented
interactively at `http://127.0.0.1:8765/docs` (Swagger UI) and
`http://127.0.0.1:8765/redoc`. This page is the curated subset you'll
actually call.

All endpoints are JSON in / JSON out. There is no authentication; the app is
intended to bind on `127.0.0.1` only.

## Conventions

- All paths are relative to `http://127.0.0.1:8765/`.
- `batch_id` arguments are batch IDs from the plan, e.g. `R7_B2`.
- `citekey` arguments are BBT citation keys, e.g. `wuComprehensiveImplementationsPhasefield2020`.
- All `*_at` timestamps are ISO 8601 in UTC (`YYYY-MM-DDTHH:MM:SSZ`).

## Meta

### `GET /api/config`

Returns the resolved paths the picker is using.

```json
{
  "repo_root": "...",
  "plan_md": "...",
  "bbt_json": "...",
  "zotsums_root": "...",
  "state_file": "...",
  "queries_file": "...",
  "inputs_dir": "...",
  "sources_dir": "..."
}
```

### `POST /api/reload`

Re-reads `zsumbib.json`, ZotSums, the plan, and both state files from disk.

```json
{
  "papers": 3619,
  "collections": 182,
  "batches": 30,
  "state_batches": 5,
  "saved_queries": 3
}
```

## Batches

### `GET /api/batches`

Returns the batch tree as a flat list, with rollup counts derived from the
state file.

```json
[
  {
    "id": "R7_B2",
    "round": 7,
    "round_title": "Phase-Field Fracture Methodology",
    "title": "Energy Decomposition & Solution Strategies",
    "node_count": 7,
    "n_nodes_parsed": 7,
    "pdf_slug": "R7_B2_pf_energy_solvers",
    "n_assigned": 12,
    "has_notebook": true,
    "notebook_id": "nb_abc123",
    "n_uploaded": 8
  },
  "..."
]
```

### `GET /api/batches/{batch_id}`

Returns the full batch detail (parsed plan + assignment + projected paper
cards).

```json
{
  "batch": {
    "id": "R7_B2",
    "round": 7,
    "round_title": "...",
    "title": "...",
    "node_count": 7,
    "pdf_slug": "...",
    "sources_text": "...",
    "zotsums_text": "...",
    "missing_text": "...",
    "cross_refs_text": "...",
    "nodes": [{"node_id": "pf-at1-regularization", "title": "...", "size": "medium"}, "..."]
  },
  "assignment": {
    "papers": ["citekey1", "..."],
    "nlm_notebook_id": "nb_abc123",
    "nlm_notebook_url": "",
    "synced_at": "2026-05-07T19:30:00Z",
    "uploaded_papers": ["citekey1"],
    "notes": ""
  },
  "papers": [{"citekey": "...", "title": "...", "...": "..."}],
  "unknown_citekeys": []
}
```

`unknown_citekeys` lists any citekey persisted in `assignment.papers` that
isn't present in the current BBT export — usually means BBT was re-exported
and a paper was renamed or removed.

### `PUT /api/batches/{batch_id}/papers`

**Replace** the entire assignment list.

```json
// request
{ "papers": ["citekey1", "citekey2", "citekey3"] }

// response
{ "papers": ["citekey1", "citekey2", "citekey3"] }
```

The list is dedup'd server-side; insertion order preserved.

### `POST /api/batches/{batch_id}/papers/add`

**Append** citekeys to the current list (no-op for already-present ones).

```json
// request
{ "citekeys": ["citekey3", "citekey4"] }

// response
{
  "papers": ["citekey1", "citekey2", "citekey3", "citekey4"],
  "added":  ["citekey4"],
  "n_added": 1
}
```

### `POST /api/batches/{batch_id}/papers/remove`

```json
// request
{ "citekeys": ["citekey2"] }

// response
{
  "papers":  ["citekey1", "citekey3"],
  "removed": ["citekey2"],
  "n_removed": 1
}
```

Removed citekeys are also stripped from the batch's `uploaded_papers` so
they'll re-upload on the next `create_notebook` run.

### `POST /api/batches/{batch_id}/papers/move`

Atomically add to `{batch_id}` and remove from `from_batch`.

```json
// request
{ "from_batch": "R7_B1", "citekeys": ["citekey1"] }

// response
{
  "target_papers": ["...existing..." , "citekey1"],
  "source_papers": ["...without citekey1..."],
  "n_added": 1,
  "n_removed_from_source": 1
}
```

`from_batch` must differ from `batch_id` (400 otherwise).

### `POST /api/batches/{batch_id}/bulk_add`

Run a [FilterSpec](../../../architecture/batch-picker.md#filterspec-serverpy) server-side and
push every match into the batch.

```json
// request
{
  "filter": {
    "q": "phase field",
    "collection": ["PFfrac"],
    "year_from": 2018,
    "only_with_pdf": true,
    "suggest_for": "R7_B2"
  },
  "mode": "add",        // "add" (union) or "replace" (drop existing)
  "limit": 1000
}

// response
{
  "papers": [...],
  "n_matched": 14,
  "n_added": 9,
  "n_removed": 0,
  "added": ["..."],
  "removed": [],
  "mode": "add"
}
```

In `replace` mode, papers that were assigned but didn't match the filter
are returned in `removed`. In both modes `papers` is the resulting list.

### `GET /api/batches/{batch_id}/compare/{other_id}`

Three-way grouping of two batches' assignments.

```json
{
  "a": "R7_B2",
  "b": "R7_B1",
  "n_a": 12,
  "n_b": 8,
  "both":   [{"citekey": "...", "title": "...", "year": "...", "has_pdf": true, "authors": ["..."]}, "..."],
  "only_a": [{"...": "..."}, "..."],
  "only_b": [{"...": "..."}, "..."]
}
```

## Papers

### `GET /api/papers`

Run a `FilterSpec` over the catalog. Identical filter semantics to
`/bulk_add` but read-only.

| Query param | Type | Default |
|-------------|------|---------|
| `q` | string | "" |
| `collection` | repeated | (none) — pass once per collection |
| `year_from` | int | (none) |
| `year_to` | int | (none) |
| `item_type` | string | "" |
| `only_with_pdf` | bool | false |
| `suggest_for` | batch ID | "" |
| `limit` | int | 500 |

```json
{
  "total": 14,             // matches across the whole catalog (pre-limit)
  "limit": 300,
  "results": [
    {
      "citekey": "...",
      "title": "...",
      "year": "2020",
      "authors": ["Wu, Jian-Ying"],
      "n_authors": 4,
      "item_type": "journalArticle",
      "paper_type": "research",
      "keywords": ["..."],
      "tags": ["..."],
      "collections": ["PFfrac", "Computational"],
      "has_pdf": true,
      "assigned_to": ["R7_B2"],
      "score": 13           // non-zero only when suggest_for is set
    }
  ]
}
```

### `GET /api/papers/{citekey}`

Returns the full [`Paper`](../../../architecture/batch-picker.md#paper-loaderspy) including
abstract, all collections/keywords/tags, and the ZotSums summary sections.

### `GET /api/collections`

```json
[
  {"name": "Computational", "parent_name": "", "paper_count": 26},
  {"name": "PFfrac",        "parent_name": "Computational", "paper_count": 55},
  "..."
]
```

Empty collections (`paper_count == 0`) are filtered out. Sorted by parent
then name.

## Saved queries

### `GET /api/saved_queries`

```json
[
  {
    "name": "phase-field-core",
    "filter": { "q": "...", "collection": ["..."], "...": "..." },
    "created_at": "2026-05-07T...",
    "updated_at": "2026-05-07T..."
  }
]
```

Sorted by name (case-insensitive).

### `PUT /api/saved_queries/{name}`

```json
// request
{ "filter": { "q": "phase field", "only_with_pdf": true, "...": "..." } }

// response — the saved query record
{
  "name": "phase-field-core",
  "filter": { "...": "..." },
  "created_at": "...",
  "updated_at": "..."
}
```

URL-encode names with special characters. Empty names (after `.strip()`)
return 400.

### `DELETE /api/saved_queries/{name}`

Returns `204 No Content` on success, `404` if the name doesn't exist.

## Pipeline actions

### `POST /api/batches/{batch_id}/export_plan`

Writes `Sources_Evals/NLM/Inputs/<slug>_plan.json`.

```json
// response
{ "path": "/abs/path/to/<slug>_plan.json", "n_papers": 12 }
```

### `POST /api/batches/{batch_id}/stage_pdfs`

```json
// request
{ "use_symlink": true }

// response
{
  "ok": true,
  "message": "Staged 11 PDFs into /.../AKMS_Sources/new/R7_B2_pf_energy_solvers",
  "target_dir": "...",
  "staged":  ["citekey1", "..."],
  "skipped": [{"citekey": "...", "reason": "no local PDF"}],
  "use_symlink": true
}
```

### `POST /api/batches/{batch_id}/create_notebook`

Runs `nlm notebook create` (if no notebook ID is recorded yet) followed by
`nlm source add --file <pdf>` for each pending paper.

```json
// request
{ "upload": true, "wait": false }

// response (200 ok)
{
  "ok": true,
  "message": "Uploaded 11 of 11 pending PDFs",
  "notebook_id": "nb_abc123",
  "uploaded": ["citekey1", "..."],
  "failures": [],
  "log": "$ nlm notebook create '...'\n...\n$ nlm source add ...\n..."
}

// response (502 on partial failure)
{
  "ok": false,
  "message": "Uploaded 9 of 11 pending PDFs (2 failed)",
  "notebook_id": "nb_abc123",
  "uploaded": ["citekey1", "..."],
  "failures": [{"citekey": "...", "reason": "..."}],
  "log": "..."
}
```

| Body field | Default | Meaning |
|------------|---------|---------|
| `upload` | true | If false, only create the notebook (capture the ID) and skip uploads. |
| `wait` | false | Pass `--wait` to `nlm source add` so each upload finishes processing before returning. Slower but better feedback. |

The notebook ID is persisted into the batch's assignment regardless of
upload outcome — so a partial failure leaves you free to retry without
recreating the notebook.

## Errors

Standard FastAPI shapes:

```json
{ "detail": "Unknown batch R99_B99" }
```

| HTTP code | When |
|-----------|------|
| `400` | Bad request (e.g. `move` with `from_batch == batch_id`, empty saved query name, unknown bulk mode) |
| `404` | Unknown batch / paper / saved query |
| `502` | `create_notebook` had at least one failure |
| `500` | Programming bug — please file an issue |
