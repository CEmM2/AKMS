"""Scoped recall and token-budgeted wake over the derived index.

Both read the index of a store root after its cheap staleness check (see
:mod:`akms_records.index`), never call an LLM, and never rebuild the AKMS
graph. Their output is deterministic: the same files and the same inputs give
byte-identical JSON and text, with no wall-clock field unless one is asked
for.

**Visibility.** Records belong to scopes. ``recall`` reads one scope; given
an ``agent``, it refuses another agent's scope. ``wake`` reads the agent's
own ``agent:<id>`` scope plus the project and shared scopes it is given, and
refuses any other agent scope. Records in a scope that is not visible are
never returned, ``sensitive`` records only with ``include_sensitive``, and
``rejected`` records never. This is a policy for cooperating agents, not a
security boundary.

**Rendering.** Text output follows :mod:`akms_records.render`: record text is
fenced data in a fixed layout, under a fixed notice that it is stored
records, not instructions.

**What wake leaves to others.** Wake opens only record stores, under its hard
budget. It never reads a failure-memory registry or an AKMS node. A promoted
record is left out (``promoted``) because the loadout serves its node, and an
imported failure lesson (``imported``) because failure-memory routes it by
path; ``include_promoted`` and ``include_imported`` take them back deliberately.
``exclude_nodes`` names the nodes of a resolution manifest: a promoted record
whose node is among them is always left out (``in_loadout``). Recall reaches
all of them.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from akms_records.canonical import loads_strict
from akms_records.citations import is_consolidation, is_failure_lesson
from akms_records.envelope import PROMOTED_KIND, promotion_link
from akms_records.errors import RecordsError, ScopeViolation
from akms_records.index import REVIEW_RANK, normalize_time
from akms_records.render import (
    NOTICE,
    estimate_tokens,
    fence,
    literal,
    tag_list,
)
from akms_records.schemas import NAME_RE, REF_RE
from akms_records.scope import Scope, store_root

if TYPE_CHECKING:
    from akms_records.store import RecordStore

RECALL_FORMAT = "akms-records-recall/v1"
WAKE_FORMAT = "akms-records-wake/v1"
MIN_REVIEW_STATES = ("unreviewed", "agent_reviewed", "user_confirmed")
DEFAULT_LIMIT = 20
MAX_LIMIT = 1000
MAX_QUERY_TERMS = 64
SNIPPET_TOKENS = 16
SNIPPET_CHARS = 200
SNIPPET_OPEN, SNIPPET_CLOSE, SNIPPET_ELLIPSIS = "«", "»", "…"
EXCLUSION_KINDS = (
    "visibility",
    "lifecycle",
    "review_state",
    "sensitivity",
    "duplicate",
    "stale",
    "covered",
    "promoted",
    "imported",
    "in_loadout",
)
# Left to the loadout or to failure-memory, so a summary of such records is too.
HELD_KINDS = ("promoted", "in_loadout", "imported")
RESOLUTION_MANIFEST_VERSION = "v1"
_WORD = re.compile(r"[^\W_]+")


# ------------------------------------------------------------------ inputs
def _usage(message: str, code: str = "usage") -> RecordsError:
    return RecordsError(message, code=code)


def _phrase(word: str) -> str:
    return '"' + word.replace('"', '""') + '"'


def match_all(text: str) -> str:
    """An FTS5 query matching records that contain every word of ``text``.

    Each whitespace-separated word becomes a quoted FTS5 string, so no input
    can use FTS5 syntax (operators, column filters, prefixes) or break the
    query. Words without a letter or digit are dropped.
    """
    if not isinstance(text, str):
        raise _usage("query must be text", "invalid_query")
    words = [word for word in text.split() if _WORD.search(word)]
    if not words:
        raise _usage("the query has no searchable words", "invalid_query")
    if len(words) > MAX_QUERY_TERMS:
        raise _usage(
            f"the query has more than {MAX_QUERY_TERMS} words", "invalid_query"
        )
    return " ".join(_phrase(word) for word in words)


def task_terms(text: str) -> list[str]:
    """Distinct words of a task description, first occurrence first."""
    seen: dict[str, None] = {}
    for word in _WORD.findall(text):
        seen.setdefault(word.casefold(), None)
        if len(seen) >= MAX_QUERY_TERMS:
            break
    return list(seen)


def match_any(text: str) -> str | None:
    """An FTS5 query matching records that contain any word of ``text``."""
    terms = task_terms(text)
    return " OR ".join(_phrase(term) for term in terms) if terms else None


def _min_rank(review_state: str) -> int:
    if review_state not in MIN_REVIEW_STATES:
        raise _usage(
            "the minimum review state must be one of " + ", ".join(MIN_REVIEW_STATES)
        )
    return REVIEW_RANK[review_state]


def _time_bound(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_time(value)
    if normalized is None:
        raise _usage(f"{name} must be an ISO 8601 date or date-time, got {value!r}")
    return normalized


def _check_agent(agent: str) -> Scope:
    if not isinstance(agent, str):
        raise _usage("agent must be text")
    return Scope("agent", agent)  # validates the ID like any scope ID


def check_visibility(scope: Scope, agent: str | None) -> None:
    """Refuse an agent reading another agent's scope."""
    if agent is None:
        return
    own = _check_agent(agent)
    if scope.kind == "agent" and scope != own:
        raise ScopeViolation(f"agent {agent} may not read {scope}")


def _json_list(text: str) -> list[Any]:
    value = json.loads(text)
    return value if isinstance(value, list) else []


def manifest_nodes(path: str | Path) -> frozenset[str]:
    """The node IDs a resolution manifest selected (``akms resolve-task`` writes it).

    Read as plain JSON, so this needs no ``akms``. A missing file is
    ``manifest_missing``; anything but a v1 manifest is ``manifest_invalid``.
    """
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        raise _usage(f"no resolution manifest at {path}", "manifest_missing") from None
    except OSError as exc:
        raise _usage(
            f"cannot read the manifest {path}: {exc.strerror}", "manifest_invalid"
        ) from None
    try:
        data = loads_strict(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise _usage(f"{path} is not valid JSON: {exc}", "manifest_invalid") from None
    selected = data.get("selected_nodes") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != RESOLUTION_MANIFEST_VERSION
        or not isinstance(selected, list)
    ):
        raise _usage(
            f"{path} is not a {RESOLUTION_MANIFEST_VERSION} resolution manifest",
            "manifest_invalid",
        )
    nodes: set[str] = set()
    for item in selected:
        node_id = item.get("node_id") if isinstance(item, dict) else None
        if not isinstance(node_id, str) or not node_id:
            raise _usage(f"{path} has a malformed selected node", "manifest_invalid")
        nodes.add(node_id)
    return frozenset(nodes)


# ------------------------------------------------------------------ recall
@dataclass(frozen=True)
class RecallHit:
    """One recall result: the record's summary, provenance and a snippet."""

    record_id: str
    revision: int
    scope: str
    schema_ref: str
    recorded_at: str
    time: str | None
    summary: str
    label: str | None
    tags: tuple[str, ...]
    sensitivity: str
    review_state: str
    lifecycle: str
    origin: dict[str, str]
    source_refs: tuple[dict[str, str], ...]
    superseded_by: str | None
    supersedes: tuple[str, ...]
    snippet: str | None
    bm25: float | None
    record: dict[str, Any] | None = None
    consolidation: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "record_id": self.record_id,
            "revision": self.revision,
            "scope": self.scope,
            "schema_ref": self.schema_ref,
            "recorded_at": self.recorded_at,
            "time": self.time,
            "summary": self.summary,
            "label": self.label,
            "tags": list(self.tags),
            "sensitivity": self.sensitivity,
            "review_state": self.review_state,
            "lifecycle": self.lifecycle,
            "origin": dict(self.origin),
            "source_refs": [dict(ref) for ref in self.source_refs],
            "superseded_by": self.superseded_by,
            "supersedes": list(self.supersedes),
            "snippet": self.snippet,
            "bm25": self.bm25,
            "consolidation": self.consolidation,
        }
        if self.record is not None:
            out["record"] = self.record
        return out


@dataclass(frozen=True)
class RecallResult:
    """The results of one recall, best first."""

    scope: str
    query: str | None
    filters: dict[str, Any]
    hits: tuple[RecallHit, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "format": RECALL_FORMAT,
            "notice": NOTICE,
            "scope": self.scope,
            "query": self.query,
            "filters": dict(self.filters),
            "count": len(self.hits),
            "results": [hit.to_json() for hit in self.hits],
        }

    def render_text(self) -> str:
        parts = [
            "# akms-records recall\n",
            "\n",
            f"> {NOTICE}\n",
            "\n",
            f"- scope: {self.scope}\n",
            f"- query: {literal(self.query)}\n",
            f"- results: {len(self.hits)}\n",
        ]
        for position, hit in enumerate(self.hits, start=1):
            parts.append(
                f"\n## {position}. {hit.record_id} (revision {hit.revision})\n\n"
            )
            parts.append(f"- schema: {hit.schema_ref}\n")
            parts.append(
                f"- origin: {hit.origin['kind']} {literal(hit.origin['actor_id'])}\n"
            )
            parts.append(f"- review_state: {hit.review_state}\n")
            parts.append(f"- lifecycle: {hit.lifecycle}\n")
            if hit.consolidation is not None:
                parts.append(f"- consolidation: {hit.consolidation['status']}\n")
            parts.append(f"- recorded_at: {hit.recorded_at}\n")
            parts.append(f"- tags: {tag_list(hit.tags)}\n")
            parts.append(f"- source_refs: {literal(list(hit.source_refs))}\n")
            parts.append("\nsummary:\n\n")
            parts.append(fence(hit.summary))
            if hit.snippet is not None:
                parts.append("\nsnippet:\n\n")
                parts.append(fence(hit.snippet))
        return "".join(parts)


def recall(
    store: RecordStore,
    *,
    query: str | None = None,
    schema: str | None = None,
    tags: Sequence[str] = (),
    since: str | None = None,
    until: str | None = None,
    review_state: str = "unreviewed",
    include_retracted: bool = False,
    include_superseded: bool = False,
    include_sensitive: bool = False,
    agent: str | None = None,
    limit: int = DEFAULT_LIMIT,
    full: bool = False,
    with_status: bool = True,
) -> RecallResult:
    """Recall records of ``store``'s scope from the index.

    With ``query``, records must contain every word of it and are ranked by
    BM25; ties, and every result without a query, are ordered by
    ``recorded_at`` (newest first), then record ID. ``since`` (inclusive) and
    ``until`` (exclusive) apply to the schema's time field where the record
    has one, and to ``recorded_at`` otherwise. By default only active records
    (chain heads) are returned, never rejected ones, and no sensitive ones.

    Summaries (schema ``consolidation``) are returned like other records, with
    their validity in ``consolidation`` (see
    :func:`akms_records.consolidate.consolidation_status`), which reads their
    sources; ``with_status=False`` skips that.
    """
    check_visibility(store.scope, agent)
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise _usage(f"limit must be an integer from 1 to {MAX_LIMIT}")
    min_rank = _min_rank(review_state)
    lower, upper = _time_bound("since", since), _time_bound("until", until)
    tag_list_ = list(tags)
    for tag in tag_list_:
        if not isinstance(tag, str) or not tag:
            raise _usage("tags must be non-empty text")
    fts = match_all(query) if query is not None else None
    where = ["r.scope = ?"]
    params: list[Any] = [str(store.scope)]
    lifecycles = ["active"]
    if include_retracted:
        lifecycles.append("retracted")
    if include_superseded:
        lifecycles.append("superseded")
    where.append(f"r.lifecycle IN ({', '.join('?' for _ in lifecycles)})")
    params.extend(lifecycles)
    where.append("r.review_rank >= ?")
    params.append(min_rank)
    if not include_sensitive:
        where.append("r.sensitivity != 'sensitive'")
    if schema is not None:
        if isinstance(schema, str) and REF_RE.fullmatch(schema):
            where.append("r.schema_ref = ?")
        elif isinstance(schema, str) and NAME_RE.fullmatch(schema):
            where.append("r.schema_name = ?")
        else:
            raise _usage(
                f"invalid schema {schema!r}: give <name> or <name>/v<N>",
                "invalid_schema_ref",
            )
        params.append(schema)
    for tag in tag_list_:
        where.append(
            "EXISTS (SELECT 1 FROM record_tags t WHERE t.tag = ? "
            "AND t.record_id = r.record_id)"
        )
        params.append(tag)
    if lower is not None:
        where.append("r.time_value >= ?")
        params.append(lower)
    if upper is not None:
        where.append("r.time_value < ?")
        params.append(upper)
    columns = (
        "r.record_id, r.revision, r.scope, r.schema_ref, r.recorded_at, "
        "r.record_time, r.summary, r.label, r.tags, r.sensitivity, "
        "r.review_state, r.lifecycle, r.origin_kind, r.origin_actor, "
        "r.source_refs, r.superseded_by, r.supersedes"
    )
    if fts is not None:
        sql = (
            f"SELECT {columns}, snippet(records_fts, -1, ?, ?, ?, ?), round(bm25(records_fts), 9) "
            "FROM records_fts JOIN records r ON r.rid = records_fts.rowid "
            f"WHERE records_fts MATCH ? AND {' AND '.join(where)} "
            "ORDER BY round(bm25(records_fts), 9), r.recorded_at DESC, r.record_id LIMIT ?"
        )
        args = [
            SNIPPET_OPEN,
            SNIPPET_CLOSE,
            SNIPPET_ELLIPSIS,
            SNIPPET_TOKENS,
            fts,
            *params,
            limit,
        ]
    else:
        sql = (
            f"SELECT {columns}, records_fts.text, NULL "
            "FROM records r JOIN records_fts ON records_fts.rowid = r.rid "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY r.recorded_at DESC, r.record_id LIMIT ?"
        )
        args = [*params, limit]
    index = store.index_for_read()
    rows: list[Any] = []
    if index is not None:
        try:
            rows = index.db.execute(sql, args).fetchall()
        except sqlite3.OperationalError as exc:
            raise _usage(f"the query cannot be run: {exc}", "invalid_query") from None
    hits = []
    for row in rows:
        snippet = row[17]
        if fts is None:
            text = " ".join(str(snippet or "").split())
            snippet = (
                text[:SNIPPET_CHARS] + SNIPPET_ELLIPSIS
                if len(text) > SNIPPET_CHARS
                else text
            ) or None
        record = None
        if full:
            try:
                record = store.get(row[0]).envelope_json()
            except RecordsError:
                record = None  # erased or changed since the index was read
        consolidation = (
            _summary_status(store, row[0])
            if with_status and is_consolidation(row[3])
            else None
        )
        hits.append(
            RecallHit(
                record_id=row[0],
                revision=row[1],
                scope=row[2],
                schema_ref=row[3],
                recorded_at=row[4],
                time=row[5],
                summary=row[6],
                label=row[7],
                tags=tuple(_json_list(row[8])),
                sensitivity=row[9],
                review_state=row[10],
                lifecycle=row[11],
                origin={"kind": row[12], "actor_id": row[13]},
                source_refs=tuple(_json_list(row[14])),
                superseded_by=row[15],
                supersedes=tuple(_json_list(row[16])),
                snippet=snippet,
                bm25=row[18],
                record=record,
                consolidation=consolidation,
            )
        )
    filters = {
        "schema": schema,
        "tags": tag_list_,
        "since": lower,
        "until": upper,
        "review_state": review_state,
        "include_retracted": include_retracted,
        "include_superseded": include_superseded,
        "include_sensitive": include_sensitive,
        "agent": agent,
        "limit": limit,
        "full": full,
    }
    return RecallResult(str(store.scope), query, filters, tuple(hits))


def _summary_status(store: RecordStore, record_id: str) -> dict[str, Any]:
    """A summary's validity for a recall hit: status, method, counts and reasons."""
    from akms_records.consolidate import consolidation_status

    try:
        status = consolidation_status(store, record_id)
    except RecordsError as exc:
        return {"status": "invalid", "problems": [{"code": exc.code}]}
    return {
        "status": status["status"],
        "method": status["method"],
        "sources": len(status["sources"]),
        "reasons": status["reasons"],
        "problems": status["problems"],
    }


# -------------------------------------------------------------------- wake
@dataclass(frozen=True)
class _Candidate:
    record_id: str
    revision: int
    scope: str
    schema_ref: str
    origin: dict[str, str]
    review_state: str
    review_rank: int
    lifecycle: str
    sensitivity: str
    recorded_at: str
    tags: tuple[str, ...]
    summary: str
    supersedes: tuple[str, ...]
    match: float
    # For a summary: its payload and what wake needs to place it.
    consolidation: dict[str, Any] | None = None
    cites: tuple[str, ...] = ()


@dataclass(frozen=True)
class WakeEntry:
    """One record included in a wake, with its rendered text and token cost.

    ``consolidation`` is ``None`` for an ordinary record. For a summary it
    holds its status (always ``valid`` in a wake), method, provider and
    assertions with their citations.
    """

    position: int
    record_id: str
    revision: int
    scope: str
    schema_ref: str
    origin: dict[str, str]
    review_state: str
    recorded_at: str
    tags: tuple[str, ...]
    summary: str
    match: float
    tokens: int
    text: str = field(repr=False)
    consolidation: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "record_id": self.record_id,
            "revision": self.revision,
            "scope": self.scope,
            "schema_ref": self.schema_ref,
            "origin": dict(self.origin),
            "review_state": self.review_state,
            "recorded_at": self.recorded_at,
            "tags": list(self.tags),
            "summary": self.summary,
            "match": self.match,
            "tokens": self.tokens,
            "consolidation": self.consolidation,
        }


@dataclass(frozen=True)
class WakeResult:
    """A wake: entries within the budget, and what was left out and why.

    ``budget_tokens`` bounds the Markdown rendering: the header, every entry
    and the footer, each counted with the AKMS estimator. The JSON form
    carries the same entries and counts. ``covered_by_summary`` maps each
    included summary to the sources it stands in for (excluded as
    ``covered``).
    """

    agent: str
    task: str
    scopes: tuple[str, ...]
    budget_tokens: int
    header: str
    footer: str
    entries: tuple[WakeEntry, ...]
    omitted_by_budget: tuple[str, ...]
    excluded: dict[str, tuple[str, ...]]
    considered: int
    covered_by_summary: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def header_tokens(self) -> int:
        return estimate_tokens(self.header)

    @property
    def footer_tokens(self) -> int:
        return estimate_tokens(self.footer)

    @property
    def used_tokens(self) -> int:
        return (
            self.header_tokens
            + sum(entry.tokens for entry in self.entries)
            + self.footer_tokens
        )

    def to_json(self, *, generated_at: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": "ok",
            "format": WAKE_FORMAT,
            "notice": NOTICE,
            "agent": self.agent,
            "task": self.task,
            "scopes": list(self.scopes),
            "budget": {
                "limit": self.budget_tokens,
                "used": self.used_tokens,
                "header": self.header_tokens,
                "entries": sum(entry.tokens for entry in self.entries),
                "footer": self.footer_tokens,
            },
            "entries": [entry.to_json() for entry in self.entries],
            "report": {
                "considered": self.considered,
                "included": _ids([entry.record_id for entry in self.entries]),
                "omitted_by_budget": _ids(self.omitted_by_budget),
                "excluded": {
                    kind: _ids(self.excluded[kind]) for kind in EXCLUSION_KINDS
                },
                "covered_by_summary": {
                    key: list(value)
                    for key, value in sorted(self.covered_by_summary.items())
                },
            },
        }
        if generated_at is not None:
            out["generated_at"] = generated_at
        return out

    def render_markdown(self) -> str:
        return self.header + "".join(entry.text for entry in self.entries) + self.footer


def _ids(ids: Iterable[str]) -> dict[str, Any]:
    values = list(ids)
    return {"count": len(values), "ids": values}


def _wake_header(agent: str, scopes: Sequence[str], budget: int) -> str:
    return (
        "# akms-records wake\n"
        "\n"
        f"> {NOTICE}\n"
        "\n"
        f"- agent: {literal(agent)}\n"
        f"- scopes: {', '.join(scopes)}\n"
        f"- budget_tokens: {budget}\n"
        "\n"
        "## Records\n"
    )


def _wake_footer(included: int, omitted: int, excluded: dict[str, int]) -> str:
    counts = ", ".join(f"{kind} {excluded[kind]}" for kind in EXCLUSION_KINDS)
    return (
        "\n"
        "## Truncation report\n"
        "\n"
        f"- included: {included}\n"
        f"- omitted_by_budget: {omitted}\n"
        f"- excluded: {counts}\n"
        "- record IDs: in the JSON output, with the sources each summary covers\n"
    )


def _wake_entry(position: int, candidate: _Candidate) -> str:
    origin = candidate.origin
    head = (
        f"\n### {position}. {candidate.record_id} (revision {candidate.revision})\n"
        "\n"
        f"- scope: {candidate.scope}\n"
        f"- schema: {candidate.schema_ref}\n"
        f"- origin: {origin['kind']} {literal(origin['actor_id'])}\n"
        f"- review_state: {candidate.review_state}\n"
        f"- recorded_at: {candidate.recorded_at}\n"
        f"- tags: {tag_list(candidate.tags)}\n"
    )
    info = candidate.consolidation
    if info is None:
        return head + "\n" + fence(candidate.summary)
    from akms_records.consolidate import assertion_lines

    body, cites = assertion_lines(info)
    return (
        head + f"- consolidation: valid, {info['method']}, "
        f"{len(info['assertions'])} assertions from {len(candidate.cites)} records\n"
        + f"- citations: {cites}\n"
        + "\n"
        + fence(body)
    )


def _summary_key(summary: str) -> str:
    return " ".join(summary.split()).casefold()


def _held_reason(sources: Iterable[str], held: dict[str, str]) -> str | None:
    """The first held reason among ``sources``, when every one of them is held."""
    reasons = [held.get(source) for source in sources]
    if not reasons or None in reasons:
        return None
    return next(kind for kind in HELD_KINDS if kind in reasons)


def _summary_candidates(
    pending: list[tuple[Path, _Candidate]],
    eligible: dict[str, _Candidate],
    excluded: dict[str, list[str]],
    *,
    min_rank: int,
    held: dict[str, str],
) -> list[_Candidate]:
    """The summaries a wake may show: valid, and eligible for this agent.

    Extractive: every cited source must itself be eligible, and the summary
    takes the lowest review rank among them. Provider: the summary itself
    must be reviewed (``agent_reviewed`` or better), since a paraphrase can
    add claims.

    A summary inherits why its sources are held back (``held``). One whose
    sources are all held is left out for that reason, whatever its method: its
    text is what the loadout or failure-memory already serves. An extractive
    summary with some held sources is left out too, for the same reason when
    those are all it lacks, and its eligible sources stand on their own. A
    reviewed provider summary with some eligible sources stays: it may say
    more than the held ones.
    """
    from akms_records.consolidate import consolidation_status
    from akms_records.store import RecordStore

    out: list[_Candidate] = []
    for root, candidate in pending:
        store = RecordStore(root, Scope.parse(candidate.scope))
        try:
            status = consolidation_status(store, candidate.record_id)
            record = store.get(candidate.record_id)
        except RecordsError:
            status, record = None, None
        finally:
            store.close()
        if status is None or record is None or status["status"] != "valid":
            excluded["stale"].append(candidate.record_id)
            continue
        cites = tuple(sorted({ref["record_id"] for ref in status["sources"]}))
        payload = record.payload
        rank = candidate.review_rank
        all_held = _held_reason(cites, held)
        if all_held is not None:
            excluded[all_held].append(candidate.record_id)
            continue
        if payload["method"] == "provider":
            if rank < max(REVIEW_RANK["agent_reviewed"], min_rank):
                excluded["review_state"].append(candidate.record_id)
                continue
        else:
            missing = [source for source in cites if source not in eligible]
            if missing:
                reason = _held_reason(missing, held) or "review_state"
                excluded[reason].append(candidate.record_id)
                continue
            rank = min(eligible[source].review_rank for source in cites)
        out.append(
            _Candidate(
                **{
                    **candidate.__dict__,
                    "review_rank": rank,
                    "consolidation": {
                        "status": "valid",
                        "method": payload["method"],
                        "provider": payload["provider"],
                        "assertions": payload["assertions"],
                    },
                    "cites": cites,
                }
            )
        )
    return out


def _hold_reason(
    schema_ref: str,
    source_refs: str,
    *,
    include_promoted: bool,
    include_imported: bool,
    loadout: frozenset[str],
) -> str | None:
    """Why wake leaves a record to the loadout or to failure-memory, if it does."""
    link = (
        promotion_link(_json_list(source_refs))
        if PROMOTED_KIND in source_refs
        else None
    )
    if link is not None:
        if link["node_id"] in loadout:
            return "in_loadout"
        if not include_promoted:
            return "promoted"
    if is_failure_lesson(schema_ref) and not include_imported:
        return "imported"
    return None


def wake(
    *,
    agent: str,
    task: str,
    budget_tokens: int,
    scopes: Sequence[Scope | str] = (),
    repo: str | Path | None = None,
    home: str | Path | None = None,
    include_sensitive: bool = False,
    review_state: str = "unreviewed",
    include_unreviewed: bool = False,
    include_promoted: bool = False,
    include_imported: bool = False,
    exclude_nodes: Iterable[str] = (),
) -> WakeResult:
    """Select records for an agent starting a task, within a token budget.

    Visible: ``agent:<agent>`` and the project and shared ``scopes`` given.

    Eligible by default: reviewed records (``agent_reviewed`` or
    ``user_confirmed``) of every visible scope, plus the agent's own
    unreviewed records: those in ``agent:<agent>`` and those whose
    ``origin.actor_id`` is the agent. Other unreviewed records are excluded
    (``review_state``); ``include_unreviewed`` admits them. ``review_state``
    is a minimum that applies on top. Rejected records are never eligible.

    Left to the loadout or to failure-memory: a record promoted into a node
    (``promoted``), unless ``include_promoted``; a record of a promoted node in
    ``exclude_nodes`` (``in_loadout``), always; an imported failure lesson
    (``imported``), unless ``include_imported``, which also admits it while
    unreviewed, as nobody reviewed it to import it.

    Summaries: a stale or invalid one is excluded (``stale``). An extractive
    summary is eligible only when every source it cites is; a provider
    summary only once it is itself reviewed; neither when all its sources are
    held back as above (it then takes their reason). When an eligible summary costs
    fewer tokens than the eligible sources it cites, it is shown at its own
    priority (its effective review rank, then match, then recency) and those
    sources are excluded as ``covered``; otherwise the summary is excluded as
    a ``duplicate``. If an included summary does not fit the budget, its
    sources compete again.

    Priority: review state (``user_confirmed`` first; reviewed records always
    above unreviewed ones), then BM25 match with any word of ``task``, then
    ``recorded_at`` (newest first), then record ID. Deduplicated: superseded
    records and records that a newer visible record names as superseded are
    left out (only chain heads remain), and of several records with the same
    summary only the first is kept. Entries are taken in priority order while
    they fit; one that does not fit is omitted and the next is tried.
    """
    own = _check_agent(agent)
    if not isinstance(task, str):
        raise _usage("task must be text")
    if type(budget_tokens) is not int or budget_tokens < 1:
        raise _usage("budget_tokens must be a positive integer")
    min_rank = _min_rank(review_state)
    loadout = frozenset(exclude_nodes)
    visible = {own}
    for item in scopes:
        scope = Scope.parse(item) if isinstance(item, str) else item
        if scope.kind == "agent" and scope != own:
            raise ScopeViolation(f"agent {agent} may not read {scope}")
        visible.add(scope)
    visible_names = {str(scope) for scope in visible}
    roots: dict[str, tuple[Path, Scope]] = {}
    for scope in sorted(visible):
        root = store_root(scope, repo=repo, home=home)
        roots.setdefault(str(root.absolute()), (root, scope))
    excluded: dict[str, list[str]] = {kind: [] for kind in EXCLUSION_KINDS}
    held: dict[str, str] = {}
    candidates: list[_Candidate] = []
    pending: list[tuple[Path, _Candidate]] = []
    seen_ids: set[str] = set()
    considered = 0
    fts = match_any(task)
    reviewed_rank = REVIEW_RANK["agent_reviewed"]
    from akms_records.store import RecordStore

    for key in sorted(roots):
        root, scope = roots[key]
        store = RecordStore(root, scope)
        try:
            index = store.index_for_read()
            if index is None:
                continue
            rows = index.db.execute(
                "SELECT record_id, revision, scope, schema_ref, origin_kind, "
                "origin_actor, review_state, review_rank, lifecycle, sensitivity, "
                "recorded_at, tags, summary, supersedes, source_refs FROM records "
                "ORDER BY record_id"
            ).fetchall()
            scores: dict[str, float] = {}
            if fts is not None:
                for record_id, score in index.db.execute(
                    "SELECT r.record_id, round(bm25(records_fts), 9) FROM records_fts "
                    "JOIN records r ON r.rid = records_fts.rowid WHERE records_fts MATCH ?",
                    (fts,),
                ):
                    scores[record_id] = abs(score)
        finally:
            store.close()
        for row in rows:
            considered += 1
            record_id = row[0]
            summary_row = is_consolidation(row[3])
            imported = is_failure_lesson(row[3])
            mine = row[2] == str(own) or row[5] == agent
            admitted = mine or include_unreviewed or (imported and include_imported)
            rank = row[7]
            hold = _hold_reason(
                row[3],
                row[14],
                include_promoted=include_promoted,
                include_imported=include_imported,
                loadout=loadout,
            )
            if row[2] not in visible_names:
                excluded["visibility"].append(record_id)
            elif record_id in seen_ids:
                excluded["duplicate"].append(record_id)
            elif row[8] != "active":
                excluded["lifecycle"].append(record_id)
            elif rank != 0 and hold is not None:
                excluded[hold].append(record_id)
                held[record_id] = hold
            elif rank == 0 or (
                not summary_row
                and (rank < min_rank or (rank < reviewed_rank and not admitted))
            ):
                excluded["review_state"].append(record_id)
            elif row[9] == "sensitive" and not include_sensitive:
                excluded["sensitivity"].append(record_id)
            else:
                candidate = _Candidate(
                    record_id=record_id,
                    revision=row[1],
                    scope=row[2],
                    schema_ref=row[3],
                    origin={"kind": row[4], "actor_id": row[5]},
                    review_state=row[6],
                    review_rank=rank,
                    lifecycle=row[8],
                    sensitivity=row[9],
                    recorded_at=row[10],
                    tags=tuple(_json_list(row[11])),
                    summary=row[12],
                    supersedes=tuple(_json_list(row[13])),
                    match=scores.get(record_id, 0.0),
                )
                if summary_row:
                    pending.append((root, candidate))
                else:
                    candidates.append(candidate)
            seen_ids.add(record_id)
    eligible = {c.record_id: c for c in candidates}
    candidates.extend(
        _summary_candidates(pending, eligible, excluded, min_rank=min_rank, held=held)
    )
    # Priority order, built from the last key to the first (sorts are stable).
    candidates.sort(key=lambda c: c.record_id)
    candidates.sort(key=lambda c: c.recorded_at, reverse=True)
    candidates.sort(key=lambda c: (-c.review_rank, -c.match))
    order = {c.record_id: (c.recorded_at, c.record_id) for c in candidates}
    replaced = {
        older
        for c in candidates
        for older in c.supersedes
        if older in order and order[older] < order[c.record_id]
    }
    kept: list[_Candidate] = []
    summaries: set[str] = set()
    for candidate in candidates:
        key = _summary_key(candidate.summary)
        if candidate.record_id in replaced or key in summaries:
            excluded["duplicate"].append(candidate.record_id)
            continue
        summaries.add(key)
        kept.append(candidate)
    queue, covered_by = _place_summaries(kept, excluded)
    scope_names = sorted(visible_names)
    header = _wake_header(agent, scope_names, budget_tokens)
    widest = int("9" * len(str(max(considered, 1))))
    reserve = estimate_tokens(
        _wake_footer(widest, widest, {kind: widest for kind in EXCLUSION_KINDS})
    )
    remaining = budget_tokens - estimate_tokens(header) - reserve
    if remaining < 0:
        raise RecordsError(
            f"a budget of {budget_tokens} tokens cannot hold the wake header and "
            f"truncation report; give at least {budget_tokens - remaining}",
            code="budget_too_small",
            details={"minimum_tokens": budget_tokens - remaining},
        )
    position_of = {c.record_id: n for n, c in enumerate(kept)}
    entries: list[WakeEntry] = []
    omitted: list[str] = []
    while queue:
        _, candidate = queue.pop(0)
        position = len(entries) + 1
        text = _wake_entry(position, candidate)
        cost = estimate_tokens(text)
        if cost > remaining:
            omitted.append(candidate.record_id)
            restored = covered_by.pop(candidate.record_id, ())
            if restored:  # the summary did not fit: its sources compete again
                queue.extend(
                    (position_of[rid], kept[position_of[rid]]) for rid in restored
                )
                queue.sort(key=lambda item: item[0])
            continue
        remaining -= cost
        entries.append(
            WakeEntry(
                position=position,
                record_id=candidate.record_id,
                revision=candidate.revision,
                scope=candidate.scope,
                schema_ref=candidate.schema_ref,
                origin=candidate.origin,
                review_state=candidate.review_state,
                recorded_at=candidate.recorded_at,
                tags=candidate.tags,
                summary=candidate.summary,
                match=candidate.match,
                tokens=cost,
                text=text,
                consolidation=candidate.consolidation,
            )
        )
    excluded["covered"] = [rid for ids in covered_by.values() for rid in ids]
    final_excluded = {kind: tuple(sorted(ids)) for kind, ids in excluded.items()}
    footer = _wake_footer(
        len(entries),
        len(omitted),
        {kind: len(ids) for kind, ids in final_excluded.items()},
    )
    return WakeResult(
        agent=agent,
        task=task,
        scopes=tuple(scope_names),
        budget_tokens=budget_tokens,
        header=header,
        footer=footer,
        entries=tuple(entries),
        omitted_by_budget=tuple(omitted),
        excluded=final_excluded,
        considered=considered,
        covered_by_summary={key: tuple(value) for key, value in covered_by.items()},
    )


def _place_summaries(
    kept: list[_Candidate], excluded: dict[str, list[str]]
) -> tuple[list[tuple[int, _Candidate]], dict[str, tuple[str, ...]]]:
    """The wake queue in priority order, with summaries standing in for sources.

    Each summary, best first, covers the cited sources that are still in
    ``kept`` and not covered by a summary before it. It is used when its
    entry costs fewer tokens than those sources' entries together, and then
    keeps its own queue position: its effective review rank (an extractive
    summary's lowest source rank, a provider summary's own), then match,
    then recency. So a summary never rises above a record of a higher review
    rank, whatever it covers. Otherwise it is excluded as a ``duplicate``.
    """
    position_of = {c.record_id: n for n, c in enumerate(kept)}
    probe = max(len(kept), 1)  # one position for all cost estimates
    covered: set[str] = set()
    covered_by: dict[str, tuple[str, ...]] = {}
    dropped: set[str] = set()
    for candidate in kept:
        if candidate.consolidation is None:
            continue
        members = sorted(
            (
                rid
                for rid in candidate.cites
                if rid in position_of
                and rid not in covered
                and kept[position_of[rid]].consolidation is None
            ),
            key=lambda rid: position_of[rid],
        )
        if not members or estimate_tokens(_wake_entry(probe, candidate)) >= sum(
            estimate_tokens(_wake_entry(probe, kept[position_of[rid]]))
            for rid in members
        ):
            excluded["duplicate"].append(candidate.record_id)
            dropped.add(candidate.record_id)
            continue
        covered.update(members)
        covered_by[candidate.record_id] = tuple(members)
    queue: list[tuple[int, _Candidate]] = []
    for candidate in kept:
        rid = candidate.record_id
        if rid in covered or rid in dropped:
            continue
        queue.append((position_of[rid], candidate))
    queue.sort(key=lambda item: item[0])
    return queue, covered_by


__all__ = [
    "EXCLUSION_KINDS",
    "MIN_REVIEW_STATES",
    "RecallHit",
    "RecallResult",
    "WakeEntry",
    "WakeResult",
    "check_visibility",
    "manifest_nodes",
    "match_all",
    "match_any",
    "recall",
    "wake",
]
