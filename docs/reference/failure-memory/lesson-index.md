# Lesson index and cards

A registry with many lessons is hard to scan by reading every record. The
lesson index groups lessons by `location.area`, `location.package` and
`location.module`, and keeps a short card for each one. An agent reads the
groups, opens the group it needs, and fetches a full record only for the
lessons it decides to act on. The registry stays canonical: a card never
replaces a record, and `failure-memory index --expand <ID>` always returns
the record from the registry.

## Turning it on

The index is controlled by one project-config key:

```toml
[compatibility]
lesson_index_version = "failure-lesson-index/v1"
```

`failure-memory init` writes it for new projects. When it is set:

- generated node titles come from the record: the first clause of
  `root_cause`, falling back to `symptom` (and then `location.line_hint`),
  capped at 85 characters at a word boundary, as `"<ID>: <title>"`. Node IDs, tags, edges,
  routes and every other front-matter field stay the same; only the
  `title` field and the body heading change;
- the node body opens with a `## Summary` section (see
  [Summarized lesson bodies](#summarized-lesson-bodies));
- `compile` also writes `lesson_index.json` and `lesson_index.md` in the
  directory that holds the route index (`paths.routes`). They are not
  written beside the generated nodes, because AKMS reads every Markdown file
  under the local-nodes root as a node, and `compile` refuses a layout that
  would put them there.

A configuration without the key keeps line-hint titles, the original node
body and writes no index.
Its config fingerprint does not change, and the frozen consumer-contract
packs are such configurations. Adding the key to an existing project changes
its fingerprint once and recompiles every node title. Removing it again
makes `check` report the index files as stale and `compile` delete them.

`refresh clean` removes the two index files when the project marks
`generated.lessons` as disposable.

## Summarized lesson bodies

AKMS loads a coactivated node (one reached through `load_with`) as a summary
taken from its `## Summary` section, and loads a node without one in full.
With the key set, every generated lesson body therefore starts:

```markdown
# L002: The scheduler iterated an unordered mapping

## Summary

- Mechanism: The scheduler iterated an unordered mapping.
- Prevention: tests/engine/test_scheduler_order.py asserts a deterministic enqueue order.
```

- `Mechanism` and `Prevention` are the first sentences of `root_cause` and
  `prevention`, by the same rule as the cards. A line whose field is empty is
  left out. When both are empty the section holds `- Symptom:` and the
  symptom's first sentence, or, with no symptom either, `- Lesson:` and the
  heading, so it is never empty.
- Those sentences are not repeated. `### Root cause` and `### Prevention`
  hold only the text after the first sentence, and a subsection with nothing
  left is omitted.
- The `## Identity` block is dropped: the ID is in the heading and in the
  front matter.
- Everything else (generated-warning and source-hash lines, Location,
  Discovery, Symptom, Fix, Timeline, References, Notes) is unchanged.

A full read is therefore no longer than before for a lesson whose root
cause or prevention is one sentence; a lesson where both run to several
sentences grows by a few characters (the `## Summary` scaffolding is about
eight characters more than the removed Identity block).

## `lesson_index.json`

The JSON file is the machine contract. It is a pure function of the
lessons, the annotations sidecar and the node namespace. It holds no
timestamps; groups are sorted by name (UTF-8 bytes), cards by lesson ID, and
the file is written with sorted keys and two-space indentation. Rebuilding
unchanged inputs gives the same bytes, so `check` stays clean.

```json
{
  "contract_version": "failure-lesson-index/v1",
  "fingerprint": "<sha256 of the document without this field>",
  "inputs": {
    "source_schema_version": 1,
    "source_sha256": "<registry digest>",
    "annotations_sha256": "<sidecar sha256, or null>"
  },
  "counts": {"areas": 3, "packages": 4, "modules": 6, "lessons": 6},
  "areas": [
    {
      "name": "src",
      "lessons": 4,
      "packages": [
        {
          "name": "engine",
          "lessons": 3,
          "modules": [
            {
              "name": "engine.scheduler",
              "lessons": 1,
              "cards": [
                {
                  "id": "L002",
                  "node_id": "example-failure-l002",
                  "title": "The scheduler iterated an unordered mapping",
                  "trigger": "tests/engine/test_scheduler_order.py::test_stable_order",
                  "mechanism": "The scheduler iterated an unordered mapping.",
                  "prevention": "tests/engine/test_scheduler_order.py asserts a deterministic enqueue order.",
                  "references": {"plan": "docs/plans/scheduler.md"},
                  "related": ["L003"],
                  "categories": ["nondeterminism"],
                  "superseded_by": null
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

A card holds:

| Field | Source |
|---|---|
| `id`, `node_id` | The lesson ID and its generated node ID |
| `title` | First clause of `root_cause`, else `symptom`, else `location.line_hint` |
| `trigger` | `found_by.trigger` |
| `mechanism` | First sentence of `root_cause` |
| `prevention` | First sentence of `prevention` |
| `references` | The non-empty `references` fields (`commit`, `issue`, `pr`, `plan`) |
| `related` | The `related` lesson IDs |
| `categories`, `superseded_by` | The annotations sidecar; `[]` and `null` without one |

An empty area, package or module is a group named `""`.

`lesson_index.md` renders the same groups and cards for people. It starts
with the configured `generated_warning` and the index fingerprint.

## Browsing: `failure-memory index`

```bash
failure-memory index [--config <path>] [--repo .]
failure-memory index [--area <area>] [--package <package>] [--module <module>] \
  [--grep <regex>] [--config <path>] [--repo .]
failure-memory index --expand <ID> [--config <path>] [--repo .]
```

Like every other command it prints JSON. There are three levels:

1. With no selector, `level` is `"groups"`: the area, package and module
   names with lesson counts, and no cards.
2. With any of `--area`, `--package`, `--module` (exact names) or `--grep`
   (a case-insensitive regular expression matched against card text,
   categories and reference IDs), `level` is `"cards"`: the matching groups
   with their cards, and `matches`, the number of cards. Selectors combine.
3. With `--expand <ID>`, `level` is `"record"`: the lesson's `location`, its
   `card`, its full registry `record`, and its `annotations`. `--expand`
   cannot be combined with a selector; an unknown ID fails with
   `unknown_lesson`.

So every lesson is two expansions from the root: a group to its cards, a
card to its record.

The command is read-only. It takes no lock and writes nothing. It rebuilds
the index in memory from the registry and the annotations sidecar, so its
answer is current even before the next `compile`, and works without the
configuration key too. Every result has `fingerprint` (of the rebuilt index)
and `sidecar`, which gives the index path and one of these `status` values:

- `current`: the published file equals the rebuilt index;
- `stale`: it differs, and `compile` will rewrite it;
- `absent`: it has not been written yet;
- `disabled`: `lesson_index_version` is not set.

## Changing the title cap

The cap is part of the compiler's output, not of the
`failure-lesson-index/v1` contract: node IDs, tags, routes and the registry
digest do not depend on it. When it changes, a project already on the contract
sees the changed titles as drift, once:

- `failure-memory check` exits 1 with status `drift`, listing the node files and
  both index files whose titles changed;
- `failure-memory refresh if-stale` recompiles them where `[generated].lessons` is
  `disposable`, so the hooks repair it without help;
- where it is `committed`, `refresh if-stale` skips lessons as it always does, so
  `check` keeps failing until `failure-memory compile` is run and its output
  committed.

## Annotations sidecar

A reviewer's later judgement about a lesson does not go into the lesson
record, whose schema is closed. It goes into a versioned sidecar next to
the registry:

| Registry | Sidecar |
|---|---|
| Schema 1 file, e.g. `.knowledge/lessons.json` | `.knowledge/lessons.annotations.json` |
| Schema 2 directory, e.g. `.knowledge/lessons/` | `.knowledge/lessons/_annotations.json` |

```json
{
  "schema_version": "failure-lesson-annotations/v1",
  "categories": {
    "nondeterminism": "Output depends on iteration or scheduling order."
  },
  "lessons": {
    "L002": {
      "categories": ["nondeterminism"],
      "contradicts": ["L007"],
      "exceptions": ["Insertion-ordered mappings are safe."],
      "superseded_by": "L011",
      "applicability": "Schedulers that fan work out to a pool."
    }
  }
}
```

All three top-level keys are required. `categories` declares the reviewed
failure-mechanism categories (lowercase, digits and hyphens) with a
description each. Every per-lesson field is optional:

- `categories` must name declared categories;
- `contradicts` lists other lessons this one disagrees with;
- `exceptions` lists cases where the lesson does not hold, kept in the order
  written;
- `superseded_by` names the lesson that replaces this one;
- `applicability` says where the lesson applies.

The sidecar is validated by `validate`, `compile`, `check` and `index`.
A lesson ID that is not in the registry (as a key, in `contradicts` or in
`superseded_by`), a lesson naming itself, or a supersession cycle fails
with `annotation_id`. Any other shape problem fails with
`annotations_schema`, and an unreadable file with `annotations_load`.

The sidecar never changes a generated node or route. It is not part of the
registry digest, so annotating a lesson does not move any node's
`source_sha256`; the index records the sidecar's own digest in
`inputs.annotations_sha256`. Cards show `categories` and `superseded_by`;
`--expand` returns every field. `registry migrate --to 2` copies a schema 1
sidecar into the new directory as `_annotations.json`, leaves the original
in place, and reports the copy as `annotations` in its result.
