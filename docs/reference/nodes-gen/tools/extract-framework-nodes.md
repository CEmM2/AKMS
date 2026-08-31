# `extract_framework_nodes.py`

Converts deepwiki-eval results into AKMS framework nodes. Parses an
evaluated results markdown file (the output of `deepwiki_eval.py`),
extracts topics and their responses, and generates one AKMS framework
node `.md` per topic with proper v2 frontmatter, cross-layer edges, and
distilled content.

## Location

`Packages/AKMS_nodes_gen/extract_framework_nodes.py`

## Run it

```bash
python Packages/AKMS_nodes_gen/extract_framework_nodes.py \
    <results_file> <output_dir> [--manifest manifest.yaml]
```

## Output layout

```
<output_dir>/
└── moose-<topic-slug>.md   # one per topic
manifest.yaml               # extraction manifest (optional)
```

## Companion script

`extract_framework_graph.py` (same folder) handles the edge / graph layer
extraction. Both are framework-node specific — i.e. they describe code
*structure* rather than domain physics, so they're separate from the
domain-node pipeline driven by the picker.

## When to use

- After running `deepwiki_eval.py` against a target framework (MOOSE, etc.).
- Output framework nodes feed into `akms_node_promote.py` the same way
  domain nodes do.

## See also

- [`akms_node_promote.py`](akms-node-promote.md) — promote the generated framework nodes into the vault
