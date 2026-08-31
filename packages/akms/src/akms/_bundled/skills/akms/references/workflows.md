# Worked workflows

Three end-to-end paths. Run them from the project AKMS is serving.

---

## A. Cold start — no knowledge yet

```bash
bash skills/akms/scripts/akms_bootstrap.sh .
```

That creates the layout and compiles an empty graph. `akms status` will report
zero nodes, which is the honest answer: there is nothing to retrieve yet.

Add the first node:

```bash
python skills/akms/scripts/new_node.py fem-assembly \
  --title "Finite-element global assembly" \
  --domain computational-mechanics \
  --tags fem assembly sparse-matrices \
  --source human --status established
```

Edit the body until it clears the bar (implementable from the node alone), then
validate and recompile:

```bash
python -m akms.tools.node_validator knowledge/local-nodes/fem-assembly.md --strict
akms status --repo .
```

---

## B. Exploratory — "what do we know about X?"

```bash
akms query fem assembly --repo . --role implementer --max-depth 2
```

Returns ranked `(node_id, node_data)` records as JSON. Ranking blends confidence
and activation count; `--role` changes which edge types are traversed and which
domains are preferred.

Turn that into context for an agent:

```bash
akms loadout my-task --repo . --phase 1 \
  --tags fem assembly --role implementer --mode routing
```

Written to `knowledge/loadouts/1-my-task-loadout.md`.

Use `--mode full` to inline content instead of referencing it — subject to the
loadout token budget (default max 8 nodes / 12000 tokens).

**What this path does not give you:** any guarantee. A tag query that returns
three nodes is not evidence that the knowledge you need exists. For that, use C.

---

## C. Mandatory coverage — "these paths must be covered"

This is the path to use when the task names files or symbols that *must* have
knowledge behind them before they are edited.

You need a task JSON and a route index. The route index maps paths/symbols to
the nodes required for them.

```bash
akms resolve-task \
  --repo . \
  --task-json dev/tasks/fix-constitutive-update.json \
  --routes knowledge/task-routes.yaml \
  --base main --head HEAD \
  --role implementer \
  --mode routing \
  --max-depth 2
```

Changed paths come either from `--base`/`--head` (git discovery) or from
`--changed-paths file.json` containing a list — a bare path string is rejected
on purpose, so a single-path case cannot silently become a character sequence.

Two artifacts land:

```text
knowledge/loadouts/<phase>-<task>-<role>-loadout.md
knowledge/resolution-manifests/<phase>-<task>-<role>-manifest.json
```

The manifest is the point. It records what was selected, the graph version, the
route-index hash, a fingerprint, and required/coactivated/advisory counts. It is
the artifact that lets a reviewer check that coverage actually happened rather
than trusting that it did.

**On failure it exits nonzero** with a structured `error_code` and does not emit
a partial loadout. That is the designed behaviour — a resolution that cannot
prove coverage must not look like one that can.

---

## D. Closing the loop

After the work is done, feed the outcome back. Without this the graph never
improves and AKMS degrades into a static file dump.

From an AgentMemory or PCD document:

```python
from akms.graph.update_graph import update_graph
update_graph(".", source_json="dev/sessions/fix-constitutive-update-agent-memory.json")
```

An `AgentMemory` carries the fields that matter here:

- `nodes_used[]` — each with `useful` and `coverage`
  (`sufficient` / `missing-detail` / `outdated`)
- `nodes_missing[]` — knowledge that should have existed but didn't
- `pitfalls_discovered[]` — new traps, with severity
- `lessons.worked[]` / `lessons.failed[]`
- `new_knowledge[]` — drafts for new nodes (they enter as `tentative`)

Nodes marked useful gain confidence; nodes marked `outdated` or
`missing-detail` decay. Propagation carries a fraction of that along edges.

Then curate:

```bash
akms promote <node-id> --repo .     # tentative -> established, once proven
akms suppress <node-id> --repo .    # stop it surfacing, keep it
akms deprecate <node-id> --repo .   # retire it
```

`nodes_missing` entries are the backlog — they are the system telling you
exactly which node to write next, ranked by the tasks that wanted it.
