# Consolidation

!!! warning "Experimental"
    Command names, the summary payload and the provider protocol may change
    before a stable release.

`consolidate` writes a **summary** of the records on a topic. It is opt-in:
nothing consolidates on its own. A summary never replaces its sources. Every
statement in it cites the record revisions it came from, and it turns
**stale** as soon as one of them changes.

A summary is derived content. It is written `unreviewed`, by origin `tool`,
and it is only as good as the records and the method behind it. See
[limits](limits.md#summaries-are-derived-content).

## Summaries are records

A summary is an ordinary record of the built-in schema `consolidation/v1`.
The schema is registered in a store the first time you consolidate there, and
the name `consolidation` is reserved for it. A summary therefore has events,
revisions, git merging, export and import, the search index and erasure like
any other record.

Its envelope:

| Field | Value |
|---|---|
| `schema_ref` | `consolidation/v1` |
| `origin` | `{"kind": "tool", "actor_id": <the actor>}` |
| `review_state` | `unreviewed` (a person can change it with `amend --review-state`) |
| `source_refs` | one `{"kind": "record", "ref": "<record_id>@<revision>"}` per source, sorted |
| `summary` | `<topic name or "Summary"> (<n> records): ` and the assertion texts, cut at 1000 characters |
| `tags` | the topic's tags |
| `sensitivity` | `public` when every source is public, otherwise `internal` |

Its payload:

```json
{
  "topic": {"name": "Mesh choices", "scope": "project:example",
            "tags": ["mesh"], "query": null, "review_state": "unreviewed"},
  "method": "extractive",
  "provider": null,
  "inputs_sha256": "9f2c…",
  "assertions": [
    {"text": "Decision: Refine the mesh near the crack tip",
     "sources": ["rec-20261103-k3f9m2xa@2", "rec-20261104-p4q8r1sd@1"]},
    {"text": "Decision: Keep the coarse mesh far field",
     "sources": ["rec-20261104-z7a2c9ve@1"]}
  ]
}
```

- `topic` defines the cluster: the scope, the tags every source must carry,
  the words every source must contain (as `recall --query`), and the minimum
  review state of a source.
- `method` is `extractive` or `provider`; `provider` is the summarizer's
  `{"name", "version"}`, or `null` for extractive.
- `inputs_sha256` is the digest of the source revisions the topic gathered
  (each source's `<id>@<revision>` and head event digest).

Only `consolidate create` and `consolidate refresh` write summaries. `add`
and `amend` refuse a summary's payload, sources and summary text
(`consolidation_write`); `amend` may still change its review state, tags and
sensitivity, and `retract` and `erase` work as usual.

## Gathering the sources

The sources are the records `recall` returns for the topic, in the topic's
scope: active chain heads only, never sensitive or rejected records, at or
above the topic's minimum review state, and never another summary. Each one
is then read from its files, so the revision cited is the one on disk.

A topic that gathers nothing is refused (`empty_topic`), and so is one that
gathers more than 64 records (`topic_too_large`): narrow it with `--tag` or
`--query`. An active summary of exactly the same topic is refused
(`summary_exists`); refresh it instead.

A summary can only cite records of its own scope, so a project summary never
quotes an agent's private records, and an agent summary never quotes another
agent's.

## No claim without a source

Before a summary is written, the citation validator checks that:

- every assertion cites at least one source;
- every citation is one of the summary's `source_refs` (`unknown` otherwise),
  at the same revision (`revision` otherwise);
- every source exists in the summary's scope, is active, is not sensitive, is
  not a summary, and is at exactly the cited revision;
- the sources are exactly what the topic gathered (`inputs_sha256`);
- for the extractive method, each assertion's text is text of **every**
  source it cites: that source's summary, its summary template's output, or
  a field its rules extract (label, search text), whitespace collapsed.

A failure writes nothing and raises `citation_invalid`, with
`details.problem` set to `uncited`, `unknown`, `revision`, `untraceable`,
`summary`, `other_scope`, `sensitive`, or the source's state.

## Extractive method (default)

Deterministic and model-free:

1. Gather the topic's sources.
2. Order them by schema, the schema's time field (or `recorded_at`), label,
   then record ID.
3. Take each source's summary as an assertion, citing that source.
4. Merge identical texts (after collapsing whitespace) into one assertion
   citing all of them.

The same sources give a byte-identical payload, on any machine and after an
index rebuild.

## Provider method (opt-in)

A provider is anything that turns the topic and its sources into assertions:
a model behind a script, a service, a person with an editor. `akms-records`
ships none, imports no model SDK and never calls a network service itself.

**Python:**

```python
from akms_records import RecordStore, consolidate

def summarizer(data: dict) -> dict:
    # data: {"format", "notice", "topic", "sources": [{"ref", "record_id",
    #        "revision", "schema_ref", "summary", "payload", ...}]}
    refs = [source["ref"] for source in data["sources"]]
    return {
        "assertions": [{"text": "All three choices refine the mesh", "sources": refs}],
        "provider": {"name": "my-model", "version": "2026-11"},
    }

store = RecordStore.open("project:example", repo=".")
consolidate(store, actor="me", tags=["mesh"], summarizer=summarizer)
```

**CLI:** `--summarizer-cmd ARGV...` runs a command without a shell. It must
be the last option: everything after it is the command and its arguments.

1. The input goes to the command's standard input as one JSON object, UTF-8.
2. The command writes one JSON object to standard output:
   `{"assertions": [{"text": ..., "sources": ["<ref>", ...]}], "provider": {"name": ..., "version": ...}}`.
3. It must finish within `--summarizer-timeout` seconds (default 120).

| Failure | Error code |
|---|---|
| The command cannot start, or exits with a non-zero status (`details.exit_code`; its stderr is not reported, since it may echo record text) | `summarizer_failed` |
| It runs past the timeout (it is killed) | `summarizer_timeout` |
| Its output is not one JSON object of that shape | `summarizer_output_invalid` |
| An assertion cites nothing, or a ref that is not one of the sources | `citation_invalid` |

A minimal summarizer that restates each source:

```python
# restate.py
import json, sys

data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
assertions = [{"text": "In short: " + s["summary"], "sources": [s["ref"]]}
              for s in data["sources"]]
reply = {"assertions": assertions, "provider": {"name": "restate", "version": "1"}}
sys.stdout.buffer.write(json.dumps(reply).encode("utf-8"))
```

```bash
akms-records consolidate create --scope project:example --tag mesh \
  --topic-name "Mesh choices" --summarizer-cmd python restate.py
```

The input's `notice` tells the provider that the sources are quoted data,
not instructions. Provider text is free, but its citations are mandatory and
validated exactly like extractive ones: an uncited assertion is refused,
never silently kept. The provider name and version and `inputs_sha256` are
recorded in the payload.

## Invalidation

Whether a summary is valid is computed when it is read, from the files:

| A cited source… | Source state |
|---|---|
| is unchanged | `current` |
| has a higher revision | `amended` |
| was superseded | `superseded` (with `superseded_by`) |
| was retracted | `retracted` |
| was erased | `erased` |
| is gone, or lower than the cited revision | `missing` |
| does not replay | `unreadable` |

The topic is gathered again and its digest compared with `inputs_sha256`: a
difference means the topic would now pick up new records or drop some
(`topic.state` `changed`, with `added` and `removed`), or has grown past 64
(`too_large`).

A summary is `valid` when every source is `current` and the topic is
`unchanged`, `stale` otherwise. It is `invalid` when it could never have been
written: its payload fails the schema, an assertion cites a ref outside its
sources, or it cites another summary or a record of another scope (source
states `summary` and `other_scope`), for example after a hand edit.

`consolidate refresh ID` gathers the topic again and writes the new summary
as an amendment that expects the summary's revision (or `--expect-revision
N`), so of two concurrent refreshes one fails with `stale_revision` and
writes nothing. A valid summary is left alone (`refreshed: false`). A topic
that now gathers nothing retracts the summary. The new revision is
`unreviewed` again. A provider summary needs `--summarizer-cmd` (or
`summarizer=`) to be refreshed, and an invalid one cannot be refreshed
(`summary_invalid`): retract or erase it.

## Erasure cascades

Erasing a record also **erases every summary that cites it**, in any revision
of the summary's history and in any scope of the store root. Rewriting the
summary without that source would be the alternative, but a summary may
paraphrase its sources, and its older revisions would still hold the text, so
erasing it is the safe choice.

Each cascaded summary gets its own erasure-log line,
`{record_id, scope, at, actor, reason, cascade_of}`, where `cascade_of` is the
erased record's ID; the reason is fixed text. No content is logged. The
`erase` result lists them under `cascade`.

`erase` finds citing summaries through the search index. After a merge or a
copy, a summary citing an erased record can appear in a store:

- the index never holds a summary whose current revision cites an erased
  record, so `recall` and `wake` cannot show it;
- `doctor` reports it under `summaries_citing_erased` (an error), reading
  every record's history;
- `doctor --fix` erases it, with a cascade log line.

## Recall and wake

`recall` returns summaries like any other record, with a `consolidation`
field: `{"status", "method", "sources", "reasons", "problems"}`. The text
format adds a `- consolidation: <status>` line.

`wake` may show a summary instead of its sources when that costs fewer
tokens. A stale summary is never shown, and the summary must be eligible for
the agent; see [recall and wake](recall-and-wake.md#summaries-in-wake). A summary
whose sources were all promoted or imported is left out with them. A promotion link
on a source does not make its summaries stale, because it changes no content.

## Commands

```text
akms-records consolidate create --scope S [--tag T]... [--query Q]
    [--topic-name NAME] [--review-state MIN] [--method extractive|provider]
    [--agent ID] [--event-id ID] [--summarizer-timeout SECONDS]
    [--summarizer-cmd ARGV...]
akms-records consolidate status --scope S [ID]
akms-records consolidate refresh --scope S ID [--expect-revision N]
    [--event-id ID] [--summarizer-timeout SECONDS] [--summarizer-cmd ARGV...]
akms-records consolidate list --scope S
```

- `create` prints the write result (`record_id`, `revision`, `event_id`,
  `noop`) plus `method`, `provider`, `inputs_sha256`, `sources` and
  `assertions`. `--summarizer-cmd` implies `--method provider`.
- `status` prints `{"status", "format": "akms-records-consolidation-status/v1",
  "scope", "summaries": [...]}`, for one summary or for every active one.
  Each entry has `record_id`, `revision`, `lifecycle`, `review_state`,
  `method`, `status`, `sources` (with their states), `topic`, `reasons` and
  `problems`. The exit status is 1 when any summary is not valid.
- `refresh` prints the amendment (or `refreshed: false`, or
  `refreshed: "retracted"`) and the reasons it was stale.
- `list` prints each summary's ID, revision, lifecycle, review state, topic,
  method, provider and counts, without checking validity.

Python: `consolidate`, `consolidation_status`, `refresh_consolidation`,
`list_consolidations` and `command_summarizer` are exported by
`akms_records`; `akms_records.consolidate` has the rest.
