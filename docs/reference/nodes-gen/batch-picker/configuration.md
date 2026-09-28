# Configuration

Every path the picker uses is resolved in the same order: the command-line
flag, then its environment variable, then a default. The defaults assume
nothing about where AKMS is installed, so `akms-pick` works from any directory.

## Inputs

| Flag | Env var | Default | What it points at |
|------|---------|---------|-------------------|
| `--plan PATH` | `AKMS_PLAN_MD` | `./generation_plan.md` | The generation plan |
| `--bibtex-json PATH` | `AKMS_BBT_JSON` | `<zsum-root>/zsumbib.json` | Zotero library exported as Better BibTeX JSON |
| `--zsum-root DIR` | `AKMS_ZOTSUMS_ROOT` | `~/ZotSums` | Optional [zsum](https://github.com/CEmM2/zotero-summarizer) vault (`Papers/`, `Collections/`) |
| `--workspace DIR` | `AKMS_PICKER_WORKSPACE` | the plan's directory | Base for the files below |

## Files the picker writes

Each defaults to a location inside the workspace and can be moved on its own.

| Env var | Default | Contents |
|---------|---------|----------|
| `AKMS_BATCH_STATE` | `<workspace>/batch_assignments.json` | Per-batch paper assignments and NotebookLM metadata |
| `AKMS_SAVED_QUERIES` | `<workspace>/saved_queries.json` | Named search filters |
| `AKMS_NLM_INPUTS` | `<workspace>/plans/` | Per-batch plan JSON from **Write plan JSON** |
| `AKMS_SOURCES_NEW` | `<workspace>/pdfs/` | Per-batch folders from **Stage PDFs** |

All paths support `~` and `$VAR` expansion. None of these files needs to exist
beforehand.

## Start-up notices

The picker never refuses to start over a missing input. Anything absent or
unreadable is printed to the terminal and shown in a banner at the top of the
page, and also returned by `GET /api/status`:

| Situation | Level | Effect |
|-----------|-------|--------|
| Plan not found or unreadable | error | No batches until fixed |
| Plan has no batch headings | warning | No batches until fixed |
| Zotero export not found | warning | Batches show; no papers to assign |
| Zotero export unreadable | error | As above |
| No zsum vault | info | Everything works; no per-paper summaries or zsum keywords |

After fixing an input, press **↻ Reload data**.

## Inspecting the resolved values

```bash
curl -sS http://127.0.0.1:8765/api/config | python -m json.tool
```

```json
{
  "workspace": "~/research",
  "plan_md": "~/research/generation_plan.md",
  "bbt_json": "~/Zotero/library.json",
  "zotsums_root": "~/ZotSums",
  "state_file": "~/research/batch_assignments.json",
  "queries_file": "~/research/saved_queries.json",
  "inputs_dir": "~/research/plans",
  "sources_dir": "~/research/pdfs"
}
```

The header bar in the UI shows a condensed version of the same information.

## Common scenarios

### Keeping the picker's files away from the plan

```bash
akms-pick --plan ~/plans/generation_plan.md --workspace ~/picker-runs/round-7
```

### Splitting state per experiment

```bash
export AKMS_BATCH_STATE=$PWD/experiment_A/batch_assignments.json
export AKMS_SAVED_QUERIES=$PWD/experiment_A/saved_queries.json
akms-pick --plan generation_plan.md
```

### An AKMS monorepo checkout

Setting `AKMS_REPO_ROOT` restores the layout the picker was first written for:
the plan at `<root>/Packages/AKMS_nodes_gen/generation_plan.md`, state and
plan JSON under `<root>/Sources_Evals/NLM/`, and staged PDFs under
`<root>/AKMS_Sources/new/`. Flags and the other variables still override it.

## Server flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--host HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` to expose on the LAN; the picker has no authentication. |
| `--port PORT` | `8765` | Bind port |
| `--no-browser` | off | Skip opening the default browser |
| `--reload` | off | uvicorn `reload=True`. Development only. |

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
