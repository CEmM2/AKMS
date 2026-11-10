"""Promotion of a reviewed record into an AKMS project-local node.

``akms-records promote <record_id> --review approved`` needs the ``[akms]`` extra.
This is the only module of the package that imports ``akms``, and it does so
inside a function, so the rest of the package loads and runs without it. Nothing
here calls an LLM. Two paths write the node:

* **Default.** A ``NewKnowledge`` goes through ``update_graph``, which fixes
  ``source: agent``, ``status: tentative``, ``confidence: 0.50`` and may append
  to a similar tentative node (its deduplication).
* **Human policy.** When the schema's stored policy says ``source: human`` and
  the record is ``user_confirmed``, a validated ``LocalNodeFrontmatter`` file is
  written with the policy's status and confidence, then the graph is rebuilt.
  This only reads the policy: nothing here can set or change one.

**Confirmation.** A write that labels text ``source: human`` needs one more step
than the approval flag: creating a node on the human path, or replacing a projection in a
human-sourced node with ``--update``. Without a ``confirm`` callable it is refused
with ``confirmation_required`` before anything is written, and it never falls back
to the default path, so nobody gets a tentative node when they asked for a human
one, or the reverse. This module never reads a terminal: only the CLI turns one
into a confirmation. The method (``tty`` or ``yes``) goes in the node's Sources.
Completing the link of a node already written labels nothing new, so it needs no
confirmation, and crash recovery works without a terminal.

Both write only under the project's knowledge directory. A knowledge directory
that overlaps the global vault is refused before anything is written.

**The link.** ``promote`` records the node with an amend event that adds a
``promoted-to`` source reference (see :mod:`akms_records.envelope`).

**Crash order: the node first, then the link.** A link without a node would drop
the record from ``wake`` with nothing serving it; a node without a link is found
again by the next run. The node's Sources section names the revision it holds,
outside any fence, so the next run scans ``local-nodes`` and completes the link
(rebuilding the graph, in case the crash came before that) instead of writing a
second node. A retried link is a no-op through its event ID.

**Idempotency.** A record whose head is its own link event has nothing new, and
promoting it again changes nothing. A newer revision of a promoted record is
refused with ``already_promoted``, naming the node, unless ``--update`` replaces its managed projection in that node.
Loadouts verify source and body fingerprints before including a projection.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from akms_records.citations import is_consolidation, is_failure_lesson
from akms_records.envelope import MAX_REFS, PROMOTED_KIND, Record, check_actor
from akms_records.errors import RecordsError
from akms_records.fsio import FILE_MODE, replace_file, write_exclusive
from akms_records.index import INDEX_DIRNAME, REVIEW_RANK
from akms_records.procs import pid_alive
from akms_records.render import fence, literal
from akms_records.schemas import parse_ref, pointer_text

if TYPE_CHECKING:
    from akms_records.store import RecordStore

REVIEW_APPROVED = "approved"
REVIEW_CHOICES = (REVIEW_APPROVED,)
MIN_REVIEW_CHOICES = ("agent_reviewed", "user_confirmed")
DEFAULT_MIN_REVIEW = "user_confirmed"
PATH_DEFAULT = "default"
PATH_HUMAN = "human-policy"
MAX_TITLE = 120
LEDGER_ATTEMPTS = 8
LOCK_NAME = "promote.lock"
CONFIRM_METHODS = ("tty", "yes")
_MARKER = re.compile(r"- record: `(rec-[0-9]{8}-[0-9a-hjkmnp-tv-z]{8})@([1-9][0-9]*)`")
_FENCE = re.compile(r"(`{3,})(.*)")
_WITHDRAWN = "<!-- akms-records-withdrawn/v1 "


# Given what a human-path write will label, returns how it was confirmed (one of
# CONFIRM_METHODS), or raises to refuse.
Confirm = Callable[[dict[str, Any]], str]


def confirm_yes(_write: dict[str, Any]) -> str:
    """Confirm without asking: what ``--yes`` means, for a deliberate caller."""
    return "yes"


def _refuse(message: str, code: str, **details: Any) -> RecordsError:
    return RecordsError(message, code=code, details=details or None)


def _load_akms() -> SimpleNamespace:
    """The AKMS functions the bridge uses, or ``akms_unavailable``."""
    try:
        import frontmatter
        from akms.graph.build_graph import (
            build_graph,
            load_graph,
            resolve_global_vault,
        )
        from akms.graph.update_graph import update_graph
        from akms.graph import record_projections
        from akms.layout import local_knowledge_dir
        from akms.schema.models import LocalNodeFrontmatter, NewKnowledge
        from akms.schema.validators import (
            parse_node_frontmatter_from_dict,
            parse_propagation_config,
        )
    except ImportError as exc:
        raise _refuse(
            "promote needs AKMS: install the extra with "
            f"pip install 'akms-records[akms]' ({exc})",
            "akms_unavailable",
        ) from None
    return SimpleNamespace(
        frontmatter=frontmatter,
        build_graph=build_graph,
        load_graph=load_graph,
        resolve_global_vault=resolve_global_vault,
        update_graph=update_graph,
        projections=record_projections,
        local_knowledge_dir=local_knowledge_dir,
        LocalNodeFrontmatter=LocalNodeFrontmatter,
        NewKnowledge=NewKnowledge,
        parse_node=parse_node_frontmatter_from_dict,
        parse_propagation_config=parse_propagation_config,
    )


# ---------------------------------------------------------------- the guard
def _vaults(akms: SimpleNamespace, knowledge: Path) -> list[Path]:
    """The global vault as AKMS would resolve it, with and without its config."""
    vaults = [akms.resolve_global_vault()]
    config_path = knowledge / "graph" / "propagation_config.yaml"
    if config_path.is_file():
        try:
            config = akms.parse_propagation_config(config_path)
        except Exception:  # noqa: BLE001 - update_graph reports a bad config itself
            config = None
        if config is not None:
            vaults.append(akms.resolve_global_vault(config=config))
    return vaults


def check_not_global_vault(akms: SimpleNamespace, knowledge: Path) -> None:
    """Refuse a knowledge directory that overlaps the global vault, read-only by rule."""
    targets = [knowledge, knowledge / "local-nodes", knowledge / "graph"]
    for vault in _vaults(akms, knowledge):
        resolved_vault = vault.resolve()
        for target in targets:
            resolved = target.resolve()
            if (
                resolved == resolved_vault
                or resolved.is_relative_to(resolved_vault)
                or resolved_vault.is_relative_to(resolved)
            ):
                raise _refuse(
                    f"the knowledge directory {knowledge} overlaps the global vault "
                    f"{vault}; automated writes to the global vault are not allowed",
                    "global_vault_target",
                )


# ---------------------------------------------------------------- the lock
@contextmanager
def _promote_lock(knowledge: Path) -> Iterator[None]:
    """One promote at a time per repository: ``update_graph`` does not lock its files.

    The lock file lives in the ignored index directory. A lock whose process
    is gone is removed; a live one fails with ``promote_locked``.
    """
    directory = knowledge / "records" / INDEX_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOCK_NAME
    for attempt in (1, 2):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        except FileExistsError:
            try:
                owner = int(path.read_text(encoding="ascii").strip() or "0")
            except (OSError, ValueError):
                owner = 0
            if attempt == 2 or (owner and pid_alive(owner)):
                raise _refuse(
                    f"another promote holds {path}", "promote_locked", pid=owner
                ) from None
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            continue
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        break
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


# ------------------------------------------------------------- finding nodes
@dataclass(frozen=True)
class NodeHit:
    """A local node whose Sources section names revisions of a record."""

    node_id: str
    path: Path
    revisions: frozenset[int]
    metadata: dict[str, Any]


def _marked_revisions(body: str, record_id: str) -> set[int]:
    """The revisions of ``record_id`` named outside any code fence of ``body``.

    Record text is fenced with a fence it cannot close, so a record cannot forge
    another record's marker.
    """
    found: set[int] = set()
    open_fence: str | None = None
    for line in body.split("\n"):
        if open_fence is not None:
            stripped = line.strip()
            if set(stripped) == {"`"} and len(stripped) >= len(open_fence):
                open_fence = None
            continue
        opening = _FENCE.fullmatch(line)
        if opening is not None:
            open_fence = opening.group(1)
            continue
        marker = _MARKER.fullmatch(line)
        if marker is not None and marker.group(1) == record_id:
            found.add(int(marker.group(2)))
    return found


def find_nodes(
    akms: SimpleNamespace,
    knowledge: Path,
    record_id: str,
    *,
    linked_node: str | None = None,
) -> list[NodeHit]:
    """Every local node that holds a revision of ``record_id``, by node ID."""
    hits: list[NodeHit] = []
    for path in sorted((knowledge / "local-nodes").rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
            if record_id not in raw and linked_node is None:
                continue
            post = akms.frontmatter.load(str(path))
        except Exception:  # noqa: BLE001 - a malformed node is build_graph's report
            continue
        revisions = _marked_revisions(str(post.content or ""), record_id)
        withdrawn = False
        # A manually edited Sources line must not hide a damaged managed block.
        for _, line in akms.projections._outside_lines(str(post.content or "")):
            if line.startswith(_WITHDRAWN) and line.rstrip().endswith(" -->"):
                try:
                    mark = json.loads(line.rstrip()[len(_WITHDRAWN) : -4])
                    withdrawn = withdrawn or mark.get("record_id") == record_id
                except (ValueError, TypeError, AttributeError):
                    pass
            if line.startswith(akms.projections.HEADER) and line.rstrip().endswith(
                " -->"
            ):
                try:
                    meta = json.loads(line.rstrip()[len(akms.projections.HEADER) : -4])
                    if (
                        meta.get("record_id") == record_id
                        and type(meta.get("revision")) is int
                    ):
                        revisions.add(meta["revision"])
                except (ValueError, TypeError, AttributeError):
                    pass
        if revisions or (
            not withdrawn
            and linked_node is not None
            and post.metadata.get("id") == linked_node
        ):
            metadata = dict(post.metadata)
            hits.append(
                NodeHit(
                    str(metadata.get("id", path.stem)),
                    path,
                    frozenset(revisions),
                    metadata,
                )
            )
    return sorted(hits, key=lambda hit: hit.node_id)


# ------------------------------------------------------------- what is written
def _title(store: RecordStore, record: Record) -> str:
    try:
        rules = store.schemas.rules(record.schema_ref)
    except RecordsError:
        rules = {}
    label = pointer_text(record.payload, rules["label"]) if "label" in rules else ""
    text = " ".join((label or record.summary).split())
    return text if len(text) <= MAX_TITLE else text[: MAX_TITLE - 1] + "…"


def _tags(record: Record) -> list[str]:
    name, _ = parse_ref(record.schema_ref)
    return list(dict.fromkeys([*record.tags, name]))


def node_body(
    record: Record, *, revision: int, actor: str, confirmation: str | None = None
) -> str:
    """The node's Markdown: summary, payload rendering and Sources.

    Summary and payload are fenced, as in recall and wake: record text is data.
    ``confirmation`` is how a human-path write was confirmed, if it was one.
    """
    confirmed = f"- confirmation: {confirmation}\n" if confirmation else ""
    references = [ref for ref in record.source_refs if ref.get("kind") != PROMOTED_KIND]
    payload = json.dumps(record.payload, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        "Promoted from a stored record. The fenced text below is quoted data.\n"
        "\n"
        "## Summary\n"
        "\n"
        f"{fence(record.summary)}"
        "\n"
        "## Payload\n"
        "\n"
        f"{fence(payload, 'json')}"
        "\n"
        "## Sources\n"
        "\n"
        f"- record: `{record.record_id}@{revision}`\n"
        f"- schema: `{record.schema_ref}`\n"
        f"- schema_sha256: `{record.schema_sha256}`\n"
        f"- scope: `{record.scope}`\n"
        f"- recorded_at: `{record.recorded_at}`\n"
        f"- origin: {record.origin['kind']} {literal(record.origin['actor_id'])}\n"
        f"- review_state: {record.review_state}\n"
        f"- promoted_by: {literal(actor)}\n"
        f"{confirmed}"
        f"- source_refs: {literal(references)}\n"
    )


# ---------------------------------------------------------------- the checks
def _check_schema(store: RecordStore, record: Record) -> None:
    try:
        schema = store.schemas.get(record.schema_ref)
    except RecordsError as exc:
        raise _refuse(
            f"record {record.record_id}: {record.schema_ref} cannot be used: {exc}",
            "schema_mismatch",
            schema_ref=record.schema_ref,
        ) from None
    if schema.schema_sha256 != record.schema_sha256:
        raise _refuse(
            f"record {record.record_id} was written against another digest of "
            f"{record.schema_ref}",
            "schema_mismatch",
            schema_ref=record.schema_ref,
        )
    try:
        schema.validate_payload(record.payload)
    except RecordsError as exc:
        raise _refuse(
            f"record {record.record_id} no longer matches {record.schema_ref}: {exc}",
            "schema_mismatch",
            schema_ref=record.schema_ref,
        ) from None


def _check_review(store: RecordStore, record: Record, min_review_state: str) -> None:
    below = REVIEW_RANK[record.review_state] < REVIEW_RANK[min_review_state]
    if is_consolidation(record.schema_ref):
        from akms_records.consolidate import consolidation_status

        if below:
            raise _refuse(
                f"summary {record.record_id} is {record.review_state}; a summary "
                f"needs {min_review_state} before it can be promoted",
                "summary_unreviewed",
                review_state=record.review_state,
                required=min_review_state,
            )
        status = consolidation_status(store, record)["status"]
        if status != "valid":
            raise _refuse(
                f"summary {record.record_id} is {status}; refresh and review it first",
                "summary_stale",
                summary_status=status,
            )
    elif below:
        raise _refuse(
            f"record {record.record_id} is {record.review_state}; promotion needs "
            f"at least {min_review_state}",
            "review_below_threshold",
            review_state=record.review_state,
            required=min_review_state,
        )


def _check_eligible(
    store: RecordStore,
    record: Record,
    *,
    min_review_state: str,
    scope_ok: bool,
    allow_sensitive: bool,
    allow_imported: bool,
) -> None:
    if store.scope.kind != "project" and not scope_ok:
        raise _refuse(
            f"record {record.record_id} is in {store.scope}; a node is project "
            "knowledge, so promoting from an agent or shared scope needs --scope-ok",
            "scope_not_project",
            scope=str(store.scope),
        )
    if record.lifecycle == "retracted":
        raise _refuse(f"record {record.record_id} is retracted", "record_retracted")
    if record.lifecycle == "superseded":
        raise _refuse(
            f"record {record.record_id} is superseded by {record.superseded_by}",
            "record_superseded",
            superseded_by=record.superseded_by,
        )
    _check_schema(store, record)
    if is_failure_lesson(record.schema_ref) and not allow_imported:
        raise _refuse(
            f"record {record.record_id} is an imported failure lesson; failure-memory "
            "already routes it, so promoting it needs --allow-imported",
            "imported_not_promotable",
        )
    if record.sensitivity == "sensitive" and not allow_sensitive:
        raise _refuse(
            f"record {record.record_id} is sensitive; a node is copied into loadouts "
            "and git, where erasure cannot reach it, so this needs --allow-sensitive",
            "record_sensitive",
        )
    _check_review(store, record, min_review_state)


def _policy_decision(store: RecordStore, record: Record) -> dict[str, Any]:
    """Which path applies, from the stored policy. Only reads it."""
    name, _ = parse_ref(record.schema_ref)
    problem = store.policies.drift(name)
    if problem:
        raise _refuse(
            f"the promotion policy of {name} cannot be trusted: {problem}",
            "policy_drift",
        )
    policy = store.policies.current(name)
    out: dict[str, Any] = {"applied": False, "schema": name}
    if policy is None:
        return {**out, "reason": "no_policy"}
    if policy["source"] != "human":
        return {**out, "reason": "agent_policy"}
    if record.review_state != "user_confirmed":
        return {**out, "reason": "record_not_human_confirmed"}
    return {
        **out,
        "applied": True,
        "reason": "human_policy",
        "source": policy["source"],
        "status": policy["status"],
        "confidence": policy["confidence"],
    }


def _check_link_fits(record: Record) -> None:
    kept = sum(ref.get("kind") != PROMOTED_KIND for ref in record.source_refs)
    if kept >= MAX_REFS:
        raise _refuse(
            f"record {record.record_id} has {kept} source references; its promotion "
            f"link would exceed the limit of {MAX_REFS}",
            "source_refs_full",
        )


# ------------------------------------------------------------------- writing
@dataclass(frozen=True)
class _Job:
    """One promotion: what it reads and where it writes."""

    akms: SimpleNamespace
    store: RecordStore
    record: Record
    repo: Path
    knowledge: Path
    actor: str
    confirmation: str | None = None

    @property
    def revision(self) -> int:
        return self.record.content_revision

    def body(self) -> str:
        body = node_body(
            self.record,
            revision=self.revision,
            actor=self.actor,
            confirmation=self.confirmation,
        )
        return self.wrap(body, self.record.revision)

    def wrap(self, body: str, source_revision: int) -> str:
        """A source fingerprint lets core refuse obsolete projections without us."""
        directory = self.store.record_dir(self.record.record_id).resolve()
        root = self.repo.resolve()
        source = (
            {"base": "repo", "path": directory.relative_to(root).as_posix()}
            if directory.is_relative_to(root)
            else {"base": "absolute", "path": str(directory)}
        )
        try:
            snapshot = self.akms.projections.source_snapshot(
                directory, max_revision=source_revision
            )
            return self.akms.projections.render_projection(
                body,
                record_id=self.record.record_id,
                revision=self.revision,
                source_revision=source_revision,
                scope=str(self.store.scope),
                source_title=_title(self.store, self.record),
                source_dir=source,
                source_sha256=snapshot,
            )
        except self.akms.projections.ProjectionError as exc:
            raise _refuse(str(exc), "projection_source_changed") from None

    def finalize(self, hit: NodeHit) -> None:
        """Seal the source snapshot after the link event, retryable after a crash."""
        current = self.store.get(self.record.record_id)
        if current.content_revision != self.revision:
            raise _refuse(
                "the source changed while promotion completed; retry after review",
                "projection_source_changed",
            )
        post = self.akms.frontmatter.load(str(hit.path))
        text = str(post.content or "")
        try:
            blocks = self.akms.projections.parse_projections(text)
            block = next(
                b
                for b in blocks
                if b.metadata["record_id"] == self.record.record_id
                and b.metadata["revision"] == self.revision
            )
            _check_block_source(self, block.metadata)
            if (
                self.akms.projections.source_snapshot(
                    self.store.record_dir(self.record.record_id),
                    max_revision=block.metadata.get(
                        "source_revision", block.metadata["revision"]
                    ),
                    prefix=True,
                )
                != block.metadata["source_sha256"]
            ):
                raise self.akms.projections.ProjectionError(
                    "source fingerprint changed"
                )
            rendered = self.wrap(block.body, current.revision)
            changed = self.akms.projections.replace_projection(
                text, self.record.record_id, rendered
            )
        except (self.akms.projections.ProjectionError, StopIteration):
            raise _refuse(
                "the promoted block changed or predates managed projections; "
                "run promote --update, resolving any manual edits first",
                "projection_conflict",
            ) from None
        if changed.rstrip("\n") != text.rstrip("\n"):
            post.content = changed
            replace_file(
                hit.path, (self.akms.frontmatter.dumps(post) + "\n").encode("utf-8")
            )

    def verify_loaded(self, node_id: str) -> None:
        graph = self.akms.load_graph(self.knowledge / "graph" / "graph.json")
        if node_id not in graph or graph.nodes[node_id].get("node_origin") != "local":
            raise _refuse(
                f"node {node_id} did not load into the graph as a local node "
                "(see the graph's warnings); nothing was linked",
                "node_not_loaded",
                node_id=node_id,
            )

    def rebuild(self, node_id: str) -> None:
        try:
            self.akms.build_graph(self.repo)
        except Exception as exc:  # noqa: BLE001 - typed here; a re-run is safe
            raise _refuse(
                f"the graph did not build: {exc}",
                "promote_graph_failed",
                node_id=node_id,
            ) from exc
        self.verify_loaded(node_id)

    def through_update_graph(
        self, *, suggested_id: str, title: str, domain: str
    ) -> tuple[str, str, dict[str, Any]]:
        """Write through ``update_graph``: the action, the node ID and details."""
        item = self.akms.NewKnowledge(
            suggested_id=suggested_id,
            title=title,
            domain=domain,
            tags=_tags(self.record),
            content_draft=self.body(),
        )
        base = f"akms-records-{self.record.record_id}-r{self.revision}"
        for attempt in range(LEDGER_ATTEMPTS):
            source = {
                "task_id": base if attempt == 0 else f"{base}-a{attempt}",
                "phase_id": 0,
                "outcome": "success",
                "new_knowledge": [item.model_dump()],
            }
            try:
                result = self.akms.update_graph(source, self.repo)
            except Exception as exc:  # noqa: BLE001 - typed here; a re-run is safe
                raise _refuse(
                    f"update_graph failed: {exc}", "promote_graph_failed"
                ) from exc
            # Replayed: the ledger names this source, yet no node holds the
            # record. An earlier write failed, or the node was removed by hand.
            if not result.get("replayed"):
                return self._outcome(result["knowledge_events"])
        raise _refuse(
            f"the AKMS replay ledger already names {base} and its retries, and no "
            "node holds this record",
            "promote_ledger_exhausted",
        )

    def _outcome(self, events: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any]]:
        written = [e for e in events if e.get("action") in ("new_node", "dedup_append")]
        if not written:
            raise _refuse(
                f"update_graph wrote no node for {self.record.record_id} (see its log)",
                "promote_write_failed",
            )
        event = written[-1]
        node_id = str(event["node_id"])
        self.verify_loaded(node_id)
        if event["action"] == "dedup_append":
            details = {"score": event.get("score"), "threshold": event.get("threshold")}
            return "dedup_appended", node_id, details
        skipped = [e for e in events if e.get("action") == "dedup_global_skip"]
        details = (
            {"local_variant_of": skipped[-1].get("merged_into")} if skipped else {}
        )
        return "created", node_id, details

    def write_human_node(
        self, *, node_id: str, title: str, domain: str, policy: dict[str, Any]
    ) -> None:
        """Write a validated ``LocalNodeFrontmatter`` file and rebuild the graph."""
        model = self.akms.LocalNodeFrontmatter(
            id=node_id,
            title=title,
            domain=domain,
            tags=_tags(self.record),
            status=policy["status"],
            confidence=policy["confidence"],
            source=policy["source"],
        )
        metadata = model.model_dump(mode="json", exclude_none=True)
        self.akms.parse_node(metadata, is_local=True, path=f"{node_id}.md")
        post = self.akms.frontmatter.Post(self.body(), **metadata)
        directory = self.knowledge / "local-nodes"
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{node_id}.md"
        data = (self.akms.frontmatter.dumps(post) + "\n").encode("utf-8")
        try:
            write_exclusive(directory, name, data)
        except FileExistsError:
            raise _refuse(
                f"{directory / name} exists and does not hold this record",
                "node_exists",
                node_id=node_id,
            ) from None
        self.rebuild(node_id)

    def update_existing(self, hit: NodeHit) -> tuple[str, str, dict[str, Any]]:
        """Replace this record's projection, never append a conflicting old fact."""
        _is_human_node(hit)
        post = self.akms.frontmatter.load(str(hit.path))
        self.akms.parse_node(dict(post.metadata), is_local=True, path=str(hit.path))
        post.content = _replace_record_block(self, str(post.content or ""), self.body())
        # A generated title follows its source; a manually changed title stays.
        previous_titles = {
            _title(self.store, r)
            for r in _past_records(self.store, self.record.record_id)
        }
        if post.metadata.get("title") in previous_titles:
            post.metadata["title"] = _title(self.store, self.record)
        data = (self.akms.frontmatter.dumps(post) + "\n").encode("utf-8")
        replace_file(hit.path, data)
        self.rebuild(hit.node_id)
        return "updated", hit.node_id, {}

    def link(
        self,
        *,
        action: str,
        node_id: str,
        path: str,
        policy: dict[str, Any],
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Record the link, last of all, and report what happened."""
        written = self.store.record_promotion(
            self.record.record_id,
            node_id=node_id,
            revision=self.revision,
            path=path,
            expected_revision=self.record.revision,
            actor=self.actor,
        )
        hits = find_nodes(self.akms, self.knowledge, self.record.record_id)
        hit = next((h for h in hits if h.node_id == node_id), None)
        if hit is None:
            raise _refuse("the linked node disappeared", "projection_conflict")
        self.finalize(hit)
        metadata = hit.metadata if hit is not None else {}
        return {
            **self.base(),
            "action": action,
            "node_id": node_id,
            "node_file": str(hit.path) if hit is not None else None,
            "path": path,
            "node": {
                "source": metadata.get("source"),
                "status": metadata.get("status"),
                "confidence": metadata.get("confidence"),
            },
            "policy": policy,
            "details": details,
            "confirmation": self.confirmation,
            "link": written.to_json(),
        }

    def base(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "record_id": self.record.record_id,
            "revision": self.revision,
            "scope": str(self.store.scope),
        }


def _path_of(hit: NodeHit) -> str:
    return PATH_HUMAN if hit.metadata.get("source") == "human" else PATH_DEFAULT


def _previous_node(hits: list[NodeHit], link: dict[str, Any] | None) -> NodeHit | None:
    """The node to continue: the one the link names, else one holding this record."""
    if link is not None:
        for hit in hits:
            if hit.node_id == link["node_id"]:
                return hit
    return hits[0] if hits else None


def _is_human_node(hit: NodeHit) -> bool:
    """Whether a projection write needs human confirmation; stale labels refuse."""
    source, status = hit.metadata.get("source"), hit.metadata.get("status")
    if source == "human" and status in ("tentative", "established"):
        return True
    if status != "tentative":
        raise _refuse(
            f"node {hit.node_id} is {source}/{status}; it no longer takes "
            "automated additions, so edit it by hand",
            "node_not_updatable",
            node_id=hit.node_id,
        )
    return False


def _past_records(store: RecordStore, record_id: str) -> list[Record]:
    """Validated historical states, used only to recognize generated legacy text."""
    from akms_records.store import fold_events

    events = store.history(record_id)
    return [fold_events(record_id, events[:i]) for i in range(1, len(events) + 1)]


def _source_matches(
    store: RecordStore, record_id: str, repo: Path, metadata: dict[str, Any]
) -> bool:
    locator = metadata["source_dir"]
    directory = Path(locator["path"])
    if locator["base"] == "repo":
        directory = repo / directory
    return (
        metadata.get("scope") == str(store.scope)
        and directory.resolve() == store.record_dir(record_id).resolve()
    )


def _check_block_source(job: _Job, metadata: dict[str, Any]) -> None:
    if not _source_matches(job.store, job.record.record_id, job.repo, metadata):
        raise _refuse(
            "the managed projection belongs to a different source store or scope",
            "projection_source_mismatch",
        )


def _replace_record_block(job: _Job, text: str, replacement: str) -> str:
    """Preserve other sources and edits; legacy upgrades require an exact match."""
    projections = job.akms.projections
    try:
        blocks = projections.parse_projections(text)
        for block in blocks:
            if block.metadata["record_id"] == job.record.record_id:
                _check_block_source(job, block.metadata)
        if any(b.metadata["record_id"] == job.record.record_id for b in blocks):
            return projections.replace_projection(
                text, job.record.record_id, replacement
            )
    except projections.ProjectionError:
        raise _refuse(
            "a managed projection was edited; reconcile it by hand before updating",
            "projection_conflict",
        ) from None
    # Older releases had no end marker. Replace only text byte-identical to a
    # rendering of a validated historical record, starting outside a code fence.
    starts: list[int] = []
    fence_char, fence_size, offset = "", 0, 0
    for line in text.splitlines(keepends=True):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence_char:
            if (
                match
                and match[1][0] == fence_char
                and len(match[1]) >= fence_size
                and not match[2].strip()
            ):
                fence_char = ""
        elif match:
            fence_char, fence_size = match[1][0], len(match[1])
        elif line.startswith(
            "Promoted from a stored record. The fenced text below is quoted data."
        ):
            starts.append(offset)
        offset += len(line)
    spans: list[tuple[int, int]] = []
    for start in starts:
        fragment = text[start:]
        actors = re.findall(r"(?m)^- promoted_by: (.+)$", fragment)
        for raw_actor in actors:
            try:
                actor = json.loads(raw_actor)
            except ValueError:
                continue
            if not isinstance(actor, str):
                continue
            for record in _past_records(job.store, job.record.record_id):
                for confirmation in (None, "tty", "yes"):
                    body = node_body(
                        record,
                        revision=record.content_revision,
                        actor=actor,
                        confirmation=confirmation,
                    ).rstrip("\n")
                    if fragment.startswith(body) and (
                        len(fragment) == len(body) or fragment[len(body)] == "\n"
                    ):
                        spans.append((start, start + len(body)))
    spans = sorted(set(spans))
    if not spans:
        raise _refuse(
            "the legacy projection is not an exact generated block; preserve and "
            "reconcile its manual edits before updating",
            "projection_conflict",
        )
    remainder = text
    for start, end in reversed(spans):
        remainder = remainder[:start] + remainder[end:]
    if _marked_revisions(remainder, job.record.record_id):
        raise _refuse(
            "some legacy projections were edited; reconcile all of this record's "
            "blocks before updating",
            "projection_conflict",
        )
    for index, (start, end) in reversed(list(enumerate(spans))):
        text = text[:start] + (replacement if index == 0 else "") + text[end:]
    return text


@dataclass(frozen=True)
class _Plan:
    """What this promotion will do. ``human`` is what a confirmation is about."""

    kind: str  # already_promoted, complete, update, human or default
    hit: NodeHit | None = None
    link: dict[str, Any] | None = None
    node_present: bool = False
    policy: dict[str, Any] = field(default_factory=dict)
    human: dict[str, Any] | None = None


def _plan(job: _Job, *, update: bool) -> _Plan:
    """Decide what this promotion is. Reads only; refuses what it may not do."""
    record, revision = job.record, job.revision
    link = record.promoted_to
    hits = find_nodes(
        job.akms,
        job.knowledge,
        record.record_id,
        linked_node=link["node_id"] if link else None,
    )
    current_nodes: set[str] = set()
    for hit in hits:
        try:
            blocks = job.akms.projections.parse_projections(
                str(job.akms.frontmatter.load(str(hit.path)).content or "")
            )
        except job.akms.projections.ProjectionError:
            raise _refuse(
                "the managed projection was edited; reconcile before updating",
                "projection_conflict",
            ) from None
        for block in blocks:
            if block.metadata["record_id"] == record.record_id:
                _check_block_source(job, block.metadata)
                try:
                    snapshot = job.akms.projections.source_snapshot(
                        job.store.record_dir(record.record_id),
                        max_revision=block.metadata.get(
                            "source_revision", block.metadata["revision"]
                        ),
                        prefix=True,
                    )
                except job.akms.projections.ProjectionError:
                    snapshot = None
                if (
                    block.metadata["revision"] == revision
                    and snapshot == block.metadata["source_sha256"]
                ):
                    current_nodes.add(hit.node_id)
    if link is not None and link["revision"] == revision:
        present = any(hit.node_id == link["node_id"] for hit in hits)
        if link["node_id"] in current_nodes or (not update and not present):
            return _Plan("already_promoted", link=link, node_present=present)
    exact = next((hit for hit in hits if hit.node_id in current_nodes), None)
    if exact is not None:  # an earlier run wrote the node and died before the link
        return _Plan("complete", hit=exact)
    previous = _previous_node(hits, link)
    known = previous.node_id if previous else link["node_id"] if link else None
    if known is not None and not update:
        raise _refuse(
            f"record {record.record_id} is already promoted into {known}; revision "
            f"{revision} needs reconciliation. Pass --update to replace its projection",
            "already_promoted",
            node_id=known,
            revision=revision,
        )
    _check_link_fits(record)
    target = {"record_id": record.record_id, "revision": revision}
    if previous is not None:
        human = None
        if _is_human_node(previous):
            human = {
                **target,
                "action": "replace",
                "node_id": previous.node_id,
                "source": previous.metadata.get("source"),
                "status": previous.metadata.get("status"),
                "confidence": previous.metadata.get("confidence"),
            }
        return _Plan("update", hit=previous, human=human)
    policy = _policy_decision(job.store, record)
    if not policy["applied"]:
        return _Plan("default", policy=policy)
    human = {
        **target,
        "action": "create",
        "node_id": record.record_id,
        "source": policy["source"],
        "status": policy["status"],
        "confidence": policy["confidence"],
    }
    return _Plan("human", policy=policy, human=human)


def _confirmation(human: dict[str, Any], confirm: Confirm | None) -> str:
    """How a human-path write was confirmed, or a refusal. Writes nothing."""
    if confirm is None:
        raise _refuse(
            f"this would write node {human['node_id']} labelled "
            f"source={human['source']}, status={human['status']}, "
            f"confidence={human['confidence']}, which needs confirmation: run on an "
            "interactive terminal or pass --yes. It does not fall back to the "
            "default agent/tentative path",
            "confirmation_required",
            node_id=human["node_id"],
        )
    method = confirm(human)
    if method not in CONFIRM_METHODS:
        raise _refuse(
            "confirm must return one of " + ", ".join(CONFIRM_METHODS), "usage"
        )
    return method


def _execute(job: _Job, plan: _Plan, *, domain: str | None) -> dict[str, Any]:
    """Carry out a plan, under the lock."""
    record = job.record
    keeps_labels = {"applied": False, "reason": "existing_node_keeps_labels"}
    if plan.kind == "already_promoted":
        assert plan.link is not None
        if plan.node_present:
            hit = next(
                h
                for h in find_nodes(job.akms, job.knowledge, record.record_id)
                if h.node_id == plan.link["node_id"]
            )
            job.finalize(hit)
        return {
            **job.base(),
            "action": "already_promoted",
            "node_id": plan.link["node_id"],
            "path": plan.link["path"],
            "node_present": plan.node_present,
            "link": None,
        }
    if plan.kind == "complete":
        assert plan.hit is not None
        job.rebuild(plan.hit.node_id)
        return job.link(
            action="link_completed",
            node_id=plan.hit.node_id,
            path=_path_of(plan.hit),
            policy=keeps_labels,
            details={},
        )
    if plan.kind == "update":
        assert plan.hit is not None
        action, node_id, details = job.update_existing(plan.hit)
        return job.link(
            action=action,
            node_id=node_id,
            path=_path_of(plan.hit),
            policy=keeps_labels,
            details=details,
        )
    node_domain = domain if domain is not None else job.store.scope.id.lower()
    title = _title(job.store, record)
    if plan.kind == "human":
        job.write_human_node(
            node_id=record.record_id,
            title=title,
            domain=node_domain,
            policy=plan.policy,
        )
        return job.link(
            action="created",
            node_id=record.record_id,
            path=PATH_HUMAN,
            policy=plan.policy,
            details={},
        )
    action, node_id, details = job.through_update_graph(
        suggested_id=record.record_id, title=title, domain=node_domain
    )
    return job.link(
        action=action,
        node_id=node_id,
        path=PATH_DEFAULT,
        policy=plan.policy,
        details=details,
    )


# ---------------------------------------------------------------- the command
def promote(
    store: RecordStore,
    record_id: str,
    *,
    review: str | None,
    repo: str | Path,
    actor: str,
    min_review_state: str = DEFAULT_MIN_REVIEW,
    scope_ok: bool = False,
    allow_sensitive: bool = False,
    allow_imported: bool = False,
    update: bool = False,
    domain: str | None = None,
    confirm: Confirm | None = None,
) -> dict[str, Any]:
    """Promote a reviewed record into a project-local node; see the module docstring.

    ``confirm`` is called with what a human-path write will label, before anything
    is written and before the lock is taken, since it may wait for a person. It
    returns ``tty`` or ``yes``, or raises to refuse. The default is not confirmed:
    such a write is refused with ``confirmation_required``. The default path never
    calls it. :func:`confirm_yes` confirms without asking.

    Raises :class:`~akms_records.errors.RecordsError` with a stable code for each
    refusal, listed in the CLI reference.
    """
    check_actor(actor)
    akms = _load_akms()
    if review not in REVIEW_CHOICES:
        raise _refuse(
            "promotion needs explicit approval: pass --review approved",
            "review_required",
        )
    if min_review_state not in MIN_REVIEW_CHOICES:
        raise _refuse(
            "the minimum review state must be one of " + ", ".join(MIN_REVIEW_CHOICES),
            "usage",
        )
    if domain is not None and not domain.strip():
        raise _refuse("domain must not be empty", "usage")
    if record_id in store.erased_ids():
        raise _refuse(f"record {record_id} was erased", "record_erased")
    repo_path = Path(repo)
    knowledge = Path(akms.local_knowledge_dir(repo_path))
    options = {
        "min_review_state": min_review_state,
        "scope_ok": scope_ok,
        "allow_sensitive": allow_sensitive,
        "allow_imported": allow_imported,
    }
    first = store.get(record_id)
    _check_eligible(store, first, **options)
    check_not_global_vault(akms, knowledge)
    planned = _plan(
        _Job(akms, store, first, repo_path, knowledge, actor), update=update
    )
    method = _confirmation(planned.human, confirm) if planned.human else None
    with _promote_lock(knowledge):
        record = store.get(record_id)  # the checks must hold for what the lock sees
        _check_eligible(store, record, **options)
        job = _Job(akms, store, record, repo_path, knowledge, actor, method)
        plan = _plan(job, update=update)
        if plan.human != planned.human:
            raise _refuse(
                f"the record, its node or its policy changed while {record_id} was "
                "being confirmed; nothing was written. Run promote again",
                "confirmation_stale",
            )
        return _execute(job, plan, domain=domain)


def _erased_in_scope(store: RecordStore) -> set[str]:
    entries, _ = store.erasure_entries()
    return {e["record_id"] for e in entries if e.get("scope") == str(store.scope)}


def promotion_status(
    store: RecordStore, record_id: str | None = None, *, repo: str | Path
) -> dict[str, Any]:
    """Read-only source/node consistency report, including known erased sources."""
    akms = _load_akms()
    root = Path(repo)
    knowledge = Path(akms.local_knowledge_dir(root))
    erased = _erased_in_scope(store)
    ids = (
        [record_id]
        if record_id is not None
        else sorted(set(store.record_ids()) | erased)
    )
    rows: list[dict[str, Any]] = []
    for rid in ids:
        record = None
        problem = None
        if rid not in erased:
            try:
                record = store.get(rid)
            except RecordsError as exc:
                if record_id is None and exc.code == "scope_violation":
                    continue
                if record_id is not None:
                    raise
                problem = exc.code
        link = record.promoted_to if record is not None else None
        hits = find_nodes(
            akms, knowledge, rid, linked_node=link["node_id"] if link else None
        )
        if record_id is None and not hits and not link and not problem:
            continue
        state = "not_promoted"
        details: list[dict[str, Any]] = []
        if problem:
            state = "source_invalid"
        elif rid in erased:
            state = "source_erased" if hits else "withdrawn"
        elif record is not None and record.lifecycle != "active":
            state = "source_" + record.lifecycle if hits else "withdrawn"
        elif not hits:
            state = "node_missing" if link else "not_promoted"
        elif not link:
            state = "unlinked"
        else:
            assert record is not None
            state = "current"
            if link["revision"] != record.content_revision:
                state = "source_changed"
            if len(hits) != 1 or hits[0].node_id != link["node_id"]:
                state = "multiple_nodes"
        for hit in hits:
            content = str(akms.frontmatter.load(str(hit.path)).content or "")
            guard = akms.projections.guard_projection_content(content, root)
            source_matches = True
            try:
                blocks = akms.projections.parse_projections(content)
                source_matches = all(
                    _source_matches(store, rid, root, block.metadata)
                    for block in blocks
                    if block.metadata["record_id"] == rid
                )
            except akms.projections.ProjectionError:
                pass  # The guard already marks malformed blocks unavailable.
            if not source_matches:
                state = "projection_source_mismatch"
            details.append(
                {
                    "node_id": hit.node_id,
                    "node_file": str(hit.path),
                    "current": guard.current and source_matches,
                    "reason": guard.reason
                    if source_matches
                    else "source store or scope mismatch",
                }
            )
            if state == "current" and (not guard.managed or not guard.current):
                state = "projection_stale"
        rows.append(
            {
                "record_id": rid,
                "revision": record.revision if record else None,
                "state": state,
                "nodes": details,
                "error": problem,
                "next": None
                if state in {"current", "not_promoted", "withdrawn"}
                else (
                    "promotion withdraw"
                    if state
                    in {"source_erased", "source_retracted", "source_superseded"}
                    else "review the source and run promote --update"
                ),
            }
        )
    return {
        "status": "drift"
        if any(r["state"] not in {"current", "not_promoted", "withdrawn"} for r in rows)
        else "ok",
        "format": "akms-records-promotion-status/v1",
        "scope": str(store.scope),
        "count": len(rows),
        "results": rows,
    }


def withdraw_promotion(
    store: RecordStore,
    record_id: str,
    *,
    repo: str | Path,
    actor: str,
    reason: str,
    expected_revision: int | None = None,
    erased: bool = False,
    confirm: Confirm | None = None,
) -> dict[str, Any]:
    """Explicitly remove intact managed projections, never erase source records.

    Active records lose the live link after node writes. Inactive records keep
    historical links. Erased sources need their scope's erasure log and --erased.
    Human-labelled nodes retain the bridge's confirmation requirement.
    """
    from akms_records.errors import StaleRevision

    check_actor(actor)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise _refuse(
            "withdrawal needs a non-empty reason up to 1000 characters", "usage"
        )
    akms = _load_akms()
    root = Path(repo)
    knowledge = Path(akms.local_knowledge_dir(root))
    check_not_global_vault(akms, knowledge)

    def source() -> Record | None:
        if erased:
            if expected_revision is not None or record_id not in _erased_in_scope(
                store
            ):
                raise _refuse(
                    "--erased needs a matching scope's erasure log and no revision",
                    "source_not_erased",
                )
            return None
        if type(expected_revision) is not int or expected_revision < 1:
            raise _refuse(
                "withdrawal needs a positive expected revision or --erased", "usage"
            )
        record = store.get(record_id)
        if expected_revision != record.revision:
            raise StaleRevision(
                record_id,
                expected=expected_revision,
                head=record.revision,
                where="withdraw",
            )
        return record

    initial = source()
    linked = initial.promoted_to["node_id"] if initial and initial.promoted_to else None
    hits = find_nodes(akms, knowledge, record_id, linked_node=linked)
    planned: dict[str, tuple[bytes, bytes]] = {}
    for hit in hits:
        before = hit.path.read_bytes()
        post = akms.frontmatter.loads(before.decode("utf-8"))
        text = str(post.content or "")
        try:
            # Unlike an update, withdrawal of erased data cannot reconstruct a
            # legacy block. Unmarked or manually edited text is never guessed.
            changed = akms.projections.replace_projection(text, record_id, "")
        except akms.projections.ProjectionError:
            raise _refuse(
                "withdrawal cannot safely identify an intact managed block; reconcile manually",
                "projection_conflict",
            ) from None
        blocks = akms.projections.parse_projections(text)
        block = next(b for b in blocks if b.metadata["record_id"] == record_id)
        if block.metadata.get("scope") != str(store.scope):
            raise _refuse("the projection belongs to another scope", "scope_violation")
        locator = block.metadata["source_dir"]
        source_dir = Path(locator["path"])
        if locator["base"] == "repo":
            source_dir = root / source_dir
        if source_dir.resolve() != store.record_dir(record_id).resolve():
            raise _refuse(
                "the projection belongs to another source store",
                "projection_source_mismatch",
            )
        if hit.metadata.get("source") == "human":
            _confirmation(
                {
                    "action": "withdraw",
                    "record_id": record_id,
                    "revision": initial.revision if initial else None,
                    "node_id": hit.node_id,
                    "source": hit.metadata.get("source"),
                    "status": hit.metadata.get("status"),
                    "confidence": hit.metadata.get("confidence"),
                },
                confirm,
            )
        if not changed.strip(" \t\r\n-"):
            changed = (
                "Record projection withdrawn. No record content remains in this node.\n"
            )
            post.metadata["title"] = "Withdrawn record projection"
        elif post.metadata.get("title") == block.metadata.get("source_title") or (
            initial is not None
            and post.metadata.get("title")
            in {_title(store, r) for r in _past_records(store, record_id)}
        ):
            post.metadata["title"] = "Knowledge with a withdrawn record projection"
        mark = json.dumps(
            {"record_id": record_id, "scope": str(store.scope)}, sort_keys=True
        )
        post.content = changed.rstrip() + "\n\n" + _WITHDRAWN + mark + " -->\n"
        akms.parse_node(dict(post.metadata), is_local=True, path=str(hit.path))
        planned[str(hit.path)] = (
            before,
            (akms.frontmatter.dumps(post) + "\n").encode("utf-8"),
        )
    with _promote_lock(knowledge):
        current = source()
        current_hits = find_nodes(akms, knowledge, record_id, linked_node=linked)
        if {str(h.path) for h in current_hits} != set(planned):
            raise _refuse(
                "the nodes changed while withdrawal was confirmed", "confirmation_stale"
            )
        for path, (before, _) in planned.items():
            if Path(path).read_bytes() != before:
                raise _refuse(
                    "the node changed while withdrawal was confirmed",
                    "confirmation_stale",
                )
        for path, (_, after) in planned.items():
            replace_file(Path(path), after)
        if (
            planned
            or erased
            or (current is not None and current.promoted_to is not None)
        ):
            try:
                akms.build_graph(root)
            except Exception as exc:
                raise _refuse(
                    "withdrawal removed node text but rebuilding failed; retry",
                    "promote_graph_failed",
                ) from exc
        link = None
        if (
            current is not None
            and current.lifecycle == "active"
            and current.promoted_to is not None
        ):
            link = store.clear_promotion(
                record_id,
                expected_revision=current.revision,
                actor=actor,
                reason=reason,
            ).to_json()
    return {
        "status": "ok",
        "action": "withdrawn" if planned or link else "already_withdrawn",
        "record_id": record_id,
        "scope": str(store.scope),
        "reason": reason,
        "nodes": [h.node_id for h in hits],
        "link": link,
        "not_reached": [
            "previously written loadouts",
            "git history, exports and backups",
        ],
    }


__all__ = [
    "DEFAULT_MIN_REVIEW",
    "MIN_REVIEW_CHOICES",
    "REVIEW_CHOICES",
    "CONFIRM_METHODS",
    "Confirm",
    "check_not_global_vault",
    "confirm_yes",
    "find_nodes",
    "node_body",
    "promote",
    "promotion_status",
    "withdraw_promotion",
]
