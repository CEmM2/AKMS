# Examples

Self-contained, offline demonstrations. Nothing here needs an API key.

- `minimal-vault/` — three demo knowledge nodes (a requires-chain with mixed
  status/confidence/source, so projections have something to rank).
- `sample-project/` — an empty project skeleton with the `knowledge/` layout
  AKMS expects.
- `expected-output/` — committed outputs of the walkthrough below, compared in
  CI by `tests/docs_examples/`.
- `standalone-runtime/` — the embedded orchestration runtime run end to end
  with an offline demo backend and auto-approved gates (needs
  `akms[orchestration]`); executed in CI by `tests/public_smoke/runtime/`.

## Walkthrough

Run from this `examples/` directory:

```bash
python -c "from akms.graph.build_graph import build_graph; \
           build_graph('sample-project', global_vault='minimal-vault/nodes')"
cd sample-project
akms status
akms query demo
akms loadout demo-task --phase 1 --tags demo
```

`expected-output/` holds the status report and query output, plus
`graph.normalized.json` — the compiled graph minus its volatile header fields
(`generated_at`; `global_vault` and `repo_id` are environment-dependent).
The demo nodes are original content, licensed CC BY 4.0.
