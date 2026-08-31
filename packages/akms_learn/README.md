# akms-learn

> **Experimental preview.** This package ships as a clearly-labeled preview:
> its API and output formats may change between minor releases, and it is not
> yet covered by the stability promises of the core `akms` package.

Learning Source Packet (LSP) compiler and exporters for the AKMS framework.

- Distribution name: `akms-learn`
- Import name: `akms_learn`
- Python: `>=3.12,<3.13`
- CLI: `akms-learn`
- Plugin entry point: `akms.plugins` / `learn`

The package depends on `akms` for read-only graph and schema access. The reverse
direction is forbidden and tested: core never imports `akms_learn`.

`nbformat` and Jinja2 are base dependencies, so notebook and HTML features work
without an extras install. The `notebook` and `html` extras remain empty
compatibility sentinels. The `nlm` extra is also a sentinel because the grounded
NotebookLM provider probes the external `nlm` executable at runtime.

See the unified documentation: `docs/getting-started/akms-learn.md`, `docs/concepts/akms-learn.md`, and `docs/reference/akms-learn/`.
