# Install & first run

## What you need

| Input | Required | What it is |
|-------|----------|------------|
| A generation plan | Yes | Markdown listing rounds, batches and the nodes each batch should produce. The format is described in [Data sources](../../reference/nodes-gen/batch-picker/data-sources.md#3-generation_planmd-the-batch-plan). It can live anywhere. |
| A Zotero library export | To assign papers | Your Zotero library exported with the Better BibTeX plugin in **Better BibTeX JSON** format. It supplies titles, abstracts, collections, tags and PDF paths. |
| [zsum](https://github.com/CEmM2/zotero-summarizer) | No | Keeps that export up to date and adds per-paper summaries and keywords, which sharpen search and batch suggestions. Without it the picker works from titles, abstracts and Zotero tags. |
| [`nlm`](https://github.com/notebooklm-py/notebooklm-py) CLI | No | Only for the button that creates a NotebookLM notebook for a batch. |

No AKMS checkout is needed. Python **3.12** is required.

## Install

```bash
uv tool install akms-nodes-gen      # puts akms-pick on your PATH
# or, into an existing environment:
pip install "akms[nodes-gen]"
```

## First run

Point the picker at your plan and your Zotero export:

```bash
akms-pick --plan ~/research/generation_plan.md \
          --bibtex-json ~/Zotero/library.json
```

The server starts on `http://127.0.0.1:8765/` and opens it in your browser.
Assignments, saved queries, exported plan JSON and staged PDFs are written to
a **workspace**, which defaults to the directory holding the plan. Pass
`--workspace DIR` to keep them elsewhere.

Every flag has an environment-variable equivalent, so a project can set them
once. See [Configuration](../../reference/nodes-gen/batch-picker/configuration.md).

| Flag | Default | Purpose |
|------|---------|---------|
| `--plan PATH` | `./generation_plan.md` | The generation plan |
| `--bibtex-json PATH` | `<zsum-root>/zsumbib.json` | Better BibTeX JSON export of your Zotero library |
| `--zsum-root DIR` | `~/ZotSums` | Optional zsum vault with per-paper summaries |
| `--workspace DIR` | the plan's directory | Where the picker writes its files |
| `--host`, `--port` | `127.0.0.1`, `8765` | Bind address |
| `--no-browser` | off | Skip opening the browser |

## If something is missing

The picker always starts. Anything it cannot find is listed in the terminal
and in a banner at the top of the page, with what to do about it:

- **No plan** — the batch list is empty until you pass `--plan`.
- **No Zotero export** — batches show, but there are no papers to assign until
  you pass `--bibtex-json`.
- **No zsum vault** — an informational note. Everything works; summaries and
  zsum keywords are simply absent.

Fix the input and press **↻ Reload data**; no restart is needed.

## From a source checkout

Contributors working on the picker itself can run it from the repository:

```bash
uv sync --all-packages
uv run akms-pick --plan path/to/generation_plan.md --bibtex-json path/to/library.json
```

## Next steps

- :material-school: **[Tutorial: populate one batch end-to-end](tutorial.md)**
- :material-cog: **[Configuration reference](../../reference/nodes-gen/batch-picker/configuration.md)** — every flag and environment variable
- :material-book-open-variant: **[UI tour](../../reference/nodes-gen/batch-picker/ui-tour.md)** — what every button does
