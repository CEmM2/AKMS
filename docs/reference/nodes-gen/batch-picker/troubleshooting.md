# Troubleshooting

Common failure modes and how to fix them.

## "Boot failed: …" toast on first load

The UI couldn't reach the API. Check:

- The server actually started — look at the terminal you launched `akms-pick`
  in for an `INFO: Uvicorn running on http://127.0.0.1:8765` line.
- You're hitting the same host/port. If you passed `--port 8766`, the
  browser tab needs to follow.
- A firewall isn't blocking `127.0.0.1`. Rare, but possible on locked-down
  corporate machines.

## "Reloaded: 0 papers, 0 collections, 0 batches"

`POST /api/reload` succeeded but found nothing. Almost always a path issue:

```bash
curl -sS http://127.0.0.1:8765/api/config | python -m json.tool
```

Check that `bbt_json` and `zotsums_root` resolve to existing files /
directories. If they don't, set the env vars (see
[Configuration](configuration.md)) and `↻ Reload data`.

## Search returns 0 papers despite filters being permissive

- **Toggle off "only with PDF"** — if your BBT export has `relativeFilePaths=true`, attachment paths won't be absolute and the picker treats them as missing.
- **Re-export `zsumbib.json`** — if the file is older than your Zotero library, papers added recently won't appear.
- **Hit ↻ Reload data** — the catalog is cached; new exports need a reload.

## Suggest score is always 0 even with batch tokens

`suggest_for` is empty. Check:

- The **suggest for this batch** checkbox in the toolbar is on.
- A batch is actually selected (the URL doesn't contain it but the UI
  state has to). If the toolbar is shown, you're on a batch.

## Pills show "no PDF" (orange tint) but Zotero says the PDF is there

The picker only accepts attachments where the BBT `path` field is:

1. **Absolute** (starts with `/`)
2. Ends with `.pdf` (case-insensitive)

If your BBT preferences have `relativeFilePaths` enabled, fix that in
Zotero → Better BibTeX preferences and re-export. The `pdf_path` field
in `/api/papers/{citekey}` will be empty until the export is corrected.

## "Could not parse notebook ID from `nlm` output"

`nlm notebook create` produced something the heuristic
`exporters._extract_id_from_output` didn't recognize. Inspect the captured
log in the toast (or the response body of `POST /create_notebook`):

```python
# server.py exporters._extract_id_from_output tries, in order:
# 1. "id" / "notebook_id" JSON field
# 2. "nb_..." token
# 3. any 20+ char [A-Za-z0-9_-] token
```

Adjust that regex once to match your `nlm` build's format.

## `nlm source add` fails with "file not found"

The PDF symlink points at a path that's been deleted/moved in Zotero.

Fix in two steps:

1. Re-export `zsumbib.json` so paths reflect the current state.
2. Click **↻ Reload data**, then **Stage PDFs** again — the picker will rewrite the symlinks against fresh paths.

If a particular paper has truly lost its PDF, you'll see it in the
`skipped` list after `Stage PDFs` and in the `failures` list after
`Create NLM notebook`. The remaining papers still upload; the failed one
stays absent from `uploaded_papers` so you can retry after you fix it.

## Compare panel says "(empty)" for a batch you know has papers

The compare panel reads from `batch_assignments.json`. If you populated the
other batch in another session and haven't reloaded, click **↻ Reload data**
or refresh the browser tab.

## After moving a paper between batches, scores look wrong

The "suggest score" is computed against the **target batch's** tokens, and
"Used in" reflects the post-move state. If the suggest toggle was on with
the *old* selected batch, the scores reflect that one's vocabulary, not
the new one. Re-trigger the search to recompute.

## I got the wrong PDFs into a notebook

Two ways to fix it:

1. **Picker-side correction** (the notebook still has wrong sources):
    - Update the assignment (`Move`/`Remove`/`Bulk replace`).
    - Delete the wrong sources directly in NotebookLM (the picker doesn't
      currently do per-source deletion via `nlm`).
    - Click **Create NLM notebook** again — it will upload the new
      additions to the same notebook ID.

2. **Reset and start over**:
    - Delete the notebook in NotebookLM (`nlm delete notebook <name>`).
    - Clear the `nlm_notebook_id` and `uploaded_papers` from
      `batch_assignments.json` for that batch (manual edit).
    - Click **Create NLM notebook** — it'll create fresh.

## Plan parser warning in UI: "10/11 nodes"

The header says `(11 nodes)` but the markdown table only has 10 rows. The
parser uses what it actually reads (10) and surfaces the discrepancy in
the meta line. Fix the plan file when convenient — this is the canonical
source of truth and the parser deliberately doesn't paper over it.

## "Application startup complete" but `/` returns 404

You're hitting the wrong path. The default page is `GET /` (not `/index.html`
or `/static/index.html`). The static directory is mounted at `/static/`
for assets; the index file is served separately by an explicit route.

## High memory while running

The catalog (3619 papers) sits at ~150-200 MB resident. That's expected.
If you see runaway growth past 500 MB, file an issue — the picker has no
caching layers that should accumulate.

## I want to start fresh

Stop the picker, then:

```bash
rm Sources_Evals/NLM/batch_assignments.json
rm Sources_Evals/NLM/saved_queries.json
# optional: clean staged PDFs
rm -rf AKMS_Sources/new/R*_B*/
```

Restart the picker. The state files will be recreated on first save.
The plan markdown is read-only to the picker — it's not affected.
