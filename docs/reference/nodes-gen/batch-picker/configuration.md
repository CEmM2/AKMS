# Configuration

The picker resolves all paths through `batch_picker.config.Paths.resolve()`.
Every path is overridable via an environment variable.

## Path table

| Env var | Default | What it points at |
|---------|---------|-------------------|
| `AKMS_REPO_ROOT` | Auto-detected (`Packages/AKMS_nodes_gen/src/akms_nodes_gen/batch_picker/config.py` walked up 5 levels) | The AKMS monorepo root — base for the other defaults |
| `AKMS_PLAN_MD` | `<repo>/Packages/AKMS_nodes_gen/generation_plan.md` | Markdown file the parser reads |
| `AKMS_BBT_JSON` | `~/ZotSums/zsumbib.json` | BetterBibTeX export with all paper metadata + PDF paths |
| `AKMS_ZOTSUMS_ROOT` | `~/ZotSums` | ZotSums Obsidian vault (Papers/, Collections/) |
| `AKMS_BATCH_STATE` | `<repo>/Sources_Evals/NLM/batch_assignments.json` | Per-batch citekey assignments + NLM metadata |
| `AKMS_SAVED_QUERIES` | `<repo>/Sources_Evals/NLM/saved_queries.json` | Named filter specs |
| `AKMS_NLM_INPUTS` | `<repo>/Sources_Evals/NLM/Inputs` | Where `Write plan JSON` outputs land |
| `AKMS_SOURCES_NEW` | `<repo>/AKMS_Sources/new` | Where `Stage PDFs` symlinks PDFs into per-batch folders |

All paths support `~` and `$VAR` expansion.

## Inspecting the resolved values

```bash
curl -sS http://127.0.0.1:8765/api/config | python -m json.tool
```

```json
{
  "repo_root": "~/AKMS",
  "plan_md": "<repo>/packages/akms_nodes_gen/generation_plan.md",
  "bbt_json": "~/zsumbib.json",
  "zotsums_root": "~/ZotSums",
  "state_file": "~/Sources_Evals/NLM/batch_assignments.json",
  "queries_file": "~/Sources_Evals/NLM/saved_queries.json",
  "inputs_dir": "~/Sources_Evals/NLM/Inputs",
  "sources_dir": "~/AKMS_Sources/new"
}
```

The header bar in the UI shows a condensed version of the same info.

## Common scenarios

### Running against a different Zotero export

```bash
export AKMS_BBT_JSON=/path/to/other-zsumbib.json
export AKMS_ZOTSUMS_ROOT=/path/to/other-vault
akms-pick
```

### Splitting state per experiment

```bash
export AKMS_BATCH_STATE=$PWD/dev/batch_assignments_experiment_A.json
export AKMS_SAVED_QUERIES=$PWD/dev/saved_queries_experiment_A.json
akms-pick
```

The state files will be created on first save; nothing else needs to change.

### Writing plan JSONs to a different folder

```bash
export AKMS_NLM_INPUTS=$PWD/dev/Inputs_review
akms-pick
```

### Pointing at a fresh checkout

If you're running from outside the repo (e.g. `uv tool install`'d globally):

```bash
export AKMS_REPO_ROOT=/path/to/AKMS
akms-pick
```

This causes every other default to recompute relative to that root.

## CLI flags (server-level)

These are flags to `akms-pick` itself, not env vars:

| Flag | Default | Purpose |
|------|---------|---------|
| `--host HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` to expose on the LAN — be aware the picker has no auth. |
| `--port PORT` | `8765` | Bind port |
| `--no-browser` | (off) | Skip auto-opening the default browser |
| `--reload` | (off) | uvicorn `reload=True`. Dev only — re-reads source files on change. |

## Security notes

!!! warning "Local-only by default"
    The picker exposes filesystem paths and triggers shell subprocesses
    (`nlm ...`). Bind it to `127.0.0.1` (the default) on a trusted machine.

    If you must run on a shared host, put it behind nginx + basic auth or
    an ssh tunnel. There is **no built-in authentication**.

!!! note "PDF symlinks"
    `Stage PDFs` writes symlinks pointing into your Zotero storage. If you
    later move or delete those PDFs in Zotero, the symlinks break — the
    extraction pipeline will report missing files.
