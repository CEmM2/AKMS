# Install & first run

## Prerequisites

| Requirement | Why | How to check |
|-------------|-----|--------------|
| Python **3.12** | Pinned in `pyproject.toml` (`>=3.12, <3.13`) | `uvpy --version` |
| [`uv`](https://docs.astral.sh/uv/) | Workspace + venv manager | `uv --version` |
| AKMS monorepo checkout | Provides `generation_plan.md` and `Sources_Evals/NLM/` | `git rev-parse --show-toplevel` |
| Zotero with BetterBibTeX export | Source of paper metadata + PDF paths | `~/.../ZotSums/zsumbib.json` exists |
| ZotSums Obsidian vault | Per-paper summaries + curated keywords | `~/.../ZotSums/Papers/` populated |
| [`nlm`](https://github.com/notebooklm-py/notebooklm-py) CLI (optional) | Required only if you want the picker to drive NLM uploads | `nlm --version` |

!!! note "Alternative paths"
    The picker reads `zsumbib.json` and the ZotSums vault from your home
    directory by default. Use environment variables (see
    [Configuration](../../reference/nodes-gen/batch-picker/configuration.md)) to point at custom
    locations — useful for CI or shared hosts.

## Install

From the AKMS repo root:

```bash
# 1. Resolve and install dependencies for the AKMS_nodes_gen workspace member
uv sync --project Packages/AKMS_nodes_gen
```

`uv sync` builds the editable install and pulls in `fastapi`, `uvicorn`,
`pydantic`, `python-frontmatter`, `pyyaml`, and `notebooklm-py[browser]`.

### Optional: install as a global tool

If you want the `akms-pick` command available from anywhere on your `PATH`:

```bash
uv tool install --editable Packages/AKMS_nodes_gen
```

That installs two equivalent executables — `akms-pick` (short) and
`akms-batch-picker` (long-form, kept for backward compat).

## First run

=== "After uv sync (per-project)"

    ```bash
    uv --project Packages/AKMS_nodes_gen run akms-pick
    ```

=== "After uv tool install (global)"

    ```bash
    akms-pick
    ```

=== "Module-style fallback"

    ```bash
    uv --project Packages/AKMS_nodes_gen run \
        python -m akms_nodes_gen.batch_picker
    ```

The server boots on `http://127.0.0.1:8765/` and opens that URL in your
default browser. Useful flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Bind port |
| `--no-browser` | (off) | Skip auto-opening the browser tab |
| `--reload` | (off) | uvicorn hot-reload on file change (dev only) |

## Sanity check

Once the page loads, you should see:

- The header bar showing the resolved plan + state file paths
- A left-pane batch tree with **30 batches** (R1_B1 … R11_B1)
- An empty right pane reading "Pick a batch on the left."

If counts are off or any path is missing, check
[Troubleshooting](../../reference/nodes-gen/batch-picker/troubleshooting.md) — most common cause is
a stale BBT export or a wrong `AKMS_BBT_JSON` override.

## Next steps

- :material-school: **[Tutorial: populate one batch end-to-end](tutorial.md)**
- :material-cog: **[Configuration reference](../../reference/nodes-gen/batch-picker/configuration.md)** — every env var
- :material-book-open-variant: **[UI tour](../../reference/nodes-gen/batch-picker/ui-tour.md)** — what every button does
