"""Deterministic audit manifests for task-knowledge resolution.

The fingerprint boundary is intentionally narrower than the task JSON. Only
fields consumed by :class:`~akms.task_context.resolve.TaskSeeds`, current
changed paths, the query role, and resolver/index/graph versions participate.
Execution state such as routing evidence, review results, and completion
metadata must not invalidate retrieval caches.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from akms.schema.models import AgentRole
from akms.task_context.query import (
    SelectionClass,
    TaskKnowledgeQueryResult,
)
from akms.task_context.resolve import (
    ResolvedSeeds,
    TaskSeeds,
    canonicalize_task_path_specs,
)

RESOLUTION_MANIFEST_SCHEMA_VERSION = "v1"
RESOLUTION_RESOLVER_VERSION = "task-knowledge-resolver-v1"

# This tuple is the explicit ownership boundary for task-JSON invalidation.
# ``changed_files`` is canonicalized separately as ``changed_paths`` because
# callers may supplement the task JSON with the current working-tree diff.
RETRIEVAL_TASK_FIELDS = (
    "scope",
    "deliverables",
    "symbols",
    "akms_tags",
    "title",
    "objective",
    "implementation_steps",
)

_SELECTION_ORDER = {
    SelectionClass.REQUIRED: 0,
    SelectionClass.COACTIVATED: 1,
    SelectionClass.ADVISORY: 2,
}


def _text_tuple(value: object) -> tuple[str, ...]:
    """Return trimmed, deduplicated text in deterministic order."""

    values: Sequence[object]
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Sequence):
        values = value
    else:
        raise TypeError("Expected text or a sequence of text values")
    return tuple(sorted({text for item in values if (text := str(item).strip())}))


def _nonempty_text(value: object, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


class ResolutionPathSpec(BaseModel):
    """One normalized path spec exactly as consumed by the resolver."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str
    kind: Literal["exact", "directory", "glob"]

    @field_validator("value", mode="before")
    @classmethod
    def _canonical_value(cls, value: object) -> str:
        return _nonempty_text(value, field_name="path spec value")


def _canonical_path_specs(
    value: Sequence[ResolutionPathSpec],
) -> tuple[ResolutionPathSpec, ...]:
    unique = {(spec.kind, spec.value): spec for spec in value}
    return tuple(unique[key] for key in sorted(unique))


class DeclaredTaskPaths(BaseModel):
    """Task fields that declare repository paths for exact retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: tuple[ResolutionPathSpec, ...] = ()
    deliverables: tuple[ResolutionPathSpec, ...] = ()

    @field_validator("scope", "deliverables")
    @classmethod
    def _canonical_specs(
        cls,
        value: tuple[ResolutionPathSpec, ...],
    ) -> tuple[ResolutionPathSpec, ...]:
        return _canonical_path_specs(value)


class RetrievalTaskFields(BaseModel):
    """Non-path task fields consumed by task seed derivation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = ""
    objective: str = ""
    implementation_steps: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    akms_tags: tuple[str, ...] = ()

    @field_validator("title", "objective", mode="before")
    @classmethod
    def _canonical_scalar(cls, value: object) -> str:
        return str(value).strip()

    @field_validator(
        "implementation_steps",
        "symbols",
        "akms_tags",
        mode="before",
    )
    @classmethod
    def _canonical_text(cls, value: object) -> tuple[str, ...]:
        return _text_tuple(value)


class ResolutionInputs(BaseModel):
    """All and only inputs that own a resolution fingerprint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    declared_paths: DeclaredTaskPaths
    changed_paths: tuple[ResolutionPathSpec, ...] = ()
    task_fields: RetrievalTaskFields
    role: str
    graph_version: str
    route_index_hash: str
    resolver_version: str

    @field_validator("changed_paths")
    @classmethod
    def _canonical_changed_paths(
        cls,
        value: tuple[ResolutionPathSpec, ...],
    ) -> tuple[ResolutionPathSpec, ...]:
        return _canonical_path_specs(value)

    @field_validator("role", mode="before")
    @classmethod
    def _canonical_role(cls, value: object) -> str:
        if isinstance(value, AgentRole):
            value = value.value
        return _nonempty_text(value, field_name="role")

    @field_validator(
        "graph_version",
        "route_index_hash",
        "resolver_version",
        mode="before",
    )
    @classmethod
    def _canonical_version(cls, value: object, info: Any) -> str:
        return _nonempty_text(value, field_name=info.field_name)


class ResolvedSeedsManifest(BaseModel):
    """Canonical resolved seed details retained for audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    advisory_tags: tuple[str, ...] = ()
    exact_mirror_node_ids: tuple[str, ...] = ()
    required_route_node_ids: tuple[str, ...] = ()
    reasons: Mapping[str, tuple[str, ...]] = Field(
        default_factory=dict,
        validate_default=True,
    )

    @field_validator(
        "advisory_tags",
        "exact_mirror_node_ids",
        "required_route_node_ids",
        mode="before",
    )
    @classmethod
    def _canonical_text(cls, value: object) -> tuple[str, ...]:
        return _text_tuple(value)

    @field_validator("reasons", mode="before")
    @classmethod
    def _canonical_reasons(
        cls,
        value: object,
    ) -> dict[str, tuple[str, ...]]:
        if not isinstance(value, Mapping):
            raise TypeError("reasons must be a mapping")
        return {
            str(node_id).strip(): _text_tuple(reasons)
            for node_id, reasons in sorted(
                value.items(),
                key=lambda item: str(item[0]),
            )
        }

    @field_validator("reasons")
    @classmethod
    def _freeze_reasons(
        cls,
        value: Mapping[str, tuple[str, ...]],
    ) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(dict(value))

    @field_serializer("reasons")
    def _serialize_reasons(
        self,
        value: Mapping[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        return dict(value)

    @model_validator(mode="after")
    def _require_exact_reasons(self) -> ResolvedSeedsManifest:
        exact_ids = self.all_exact_node_ids
        missing = tuple(
            node_id for node_id in exact_ids if not self.reasons.get(node_id)
        )
        if missing:
            raise ValueError(
                "Every exact resolved seed requires reasons: " + ", ".join(missing)
            )
        if set(self.reasons) != set(exact_ids):
            raise ValueError("Resolved seed reasons must belong to exact node IDs")
        return self

    @property
    def all_exact_node_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(set(self.exact_mirror_node_ids) | set(self.required_route_node_ids))
        )

    @classmethod
    def from_resolved(cls, seeds: ResolvedSeeds) -> ResolvedSeedsManifest:
        if not isinstance(seeds, ResolvedSeeds):
            raise TypeError("resolved_seeds must be ResolvedSeeds")
        return cls(
            advisory_tags=seeds.advisory_tags,
            exact_mirror_node_ids=seeds.exact_mirror_node_ids,
            required_route_node_ids=seeds.required_route_node_ids,
            reasons=seeds.reasons,
        )


class ResolutionSelectedNode(BaseModel):
    """Manifest-safe selection metadata, excluding volatile node data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    selection_class: SelectionClass
    reasons: tuple[str, ...]

    @field_validator("node_id", mode="before")
    @classmethod
    def _canonical_node_id(cls, value: object) -> str:
        return _nonempty_text(value, field_name="node_id")

    @field_validator("reasons", mode="before")
    @classmethod
    def _canonical_reasons(cls, value: object) -> tuple[str, ...]:
        reasons = _text_tuple(value)
        if not reasons:
            raise ValueError("Selected nodes require at least one reason")
        return reasons


class ResolutionManifest(BaseModel):
    """Deterministic record of one task-knowledge resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = RESOLUTION_MANIFEST_SCHEMA_VERSION
    generated_at: datetime
    fingerprint: str
    inputs: ResolutionInputs
    resolved_seeds: ResolvedSeedsManifest
    selected_nodes: tuple[ResolutionSelectedNode, ...]

    @field_validator("generated_at")
    @classmethod
    def _canonical_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include a timezone")
        return value.astimezone(UTC)

    @field_validator("fingerprint", mode="before")
    @classmethod
    def _canonical_fingerprint(cls, value: object) -> str:
        fingerprint = _nonempty_text(value, field_name="fingerprint").lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError("fingerprint must be a lowercase SHA-256 digest")
        return fingerprint

    @field_validator("selected_nodes", mode="before")
    @classmethod
    def _require_selected_nodes(cls, value: object) -> object:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return value
        raise TypeError("selected_nodes must be a sequence")

    @field_validator("selected_nodes")
    @classmethod
    def _canonical_selected_nodes(
        cls,
        value: tuple[ResolutionSelectedNode, ...],
    ) -> tuple[ResolutionSelectedNode, ...]:
        return tuple(
            sorted(
                value,
                key=lambda selection: (
                    _SELECTION_ORDER[selection.selection_class],
                    selection.node_id,
                ),
            )
        )

    @model_validator(mode="after")
    def _validate_manifest(self) -> ResolutionManifest:
        expected_fingerprint = fingerprint_resolution_inputs(self.inputs)
        if self.fingerprint != expected_fingerprint:
            raise ValueError("fingerprint does not match manifest inputs")

        node_ids = tuple(selection.node_id for selection in self.selected_nodes)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("selected_nodes must contain unique node IDs")

        class_order = tuple(
            _SELECTION_ORDER[selection.selection_class]
            for selection in self.selected_nodes
        )
        if class_order != tuple(sorted(class_order)):
            raise ValueError(
                "selected_nodes must be ordered required, coactivated, then advisory"
            )

        required_selections = {
            selection.node_id: selection
            for selection in self.selected_nodes
            if selection.selection_class is SelectionClass.REQUIRED
        }
        if set(required_selections) != set(self.resolved_seeds.all_exact_node_ids):
            raise ValueError(
                "Required selections must exactly match exact resolved nodes"
            )
        reason_drift = tuple(
            node_id
            for node_id, selection in sorted(required_selections.items())
            if selection.reasons != self.resolved_seeds.reasons[node_id]
        )
        if reason_drift:
            raise ValueError(
                "Required selection reasons must exactly match resolved seed "
                "reasons: " + ", ".join(reason_drift)
            )
        return self


class StaleResolutionManifestError(ValueError):
    """Raised when current retrieval inputs no longer match a manifest."""

    def __init__(
        self,
        *,
        manifest_fingerprint: str,
        current_fingerprint: str,
    ):
        self.manifest_fingerprint = manifest_fingerprint
        self.current_fingerprint = current_fingerprint
        super().__init__(
            "Resolution manifest is stale: "
            f"stored={manifest_fingerprint}, current={current_fingerprint}"
        )


def _task_seeds(
    task: TaskSeeds | Mapping[str, Any],
    *,
    changed_paths: Sequence[str] | None,
) -> TaskSeeds:
    if isinstance(changed_paths, (str, bytes)):
        raise TypeError("changed_paths must be a sequence of path strings")
    if isinstance(task, Mapping):
        return TaskSeeds.from_task(task, changed_files=changed_paths)
    if not isinstance(task, TaskSeeds):
        raise TypeError("task must be TaskSeeds or a task mapping")
    if not changed_paths:
        return task
    return TaskSeeds(
        scope=task.scope,
        deliverables=task.deliverables,
        changed_files=task.changed_files + tuple(changed_paths),
        symbols=task.symbols,
        advisory_tags=task.advisory_tags,
        title=task.title,
        objective=task.objective,
        implementation_steps=task.implementation_steps,
    )


def canonicalize_resolution_inputs(
    *,
    task: TaskSeeds | Mapping[str, Any],
    agent_role: AgentRole | str,
    graph_version: str,
    route_index_hash: str,
    changed_paths: Sequence[str] | None = None,
    resolver_version: str = RESOLUTION_RESOLVER_VERSION,
) -> ResolutionInputs:
    """Extract the explicit retrieval-owned subset of current task inputs."""

    seeds = _task_seeds(task, changed_paths=changed_paths)
    specs = canonicalize_task_path_specs(seeds)

    def specs_for(source: str) -> tuple[ResolutionPathSpec, ...]:
        return tuple(
            ResolutionPathSpec(value=spec.value, kind=spec.kind)
            for spec in specs
            if spec.source == source
        )

    return ResolutionInputs(
        declared_paths=DeclaredTaskPaths(
            scope=specs_for("scope"),
            deliverables=specs_for("deliverable"),
        ),
        changed_paths=specs_for("changed_file"),
        task_fields=RetrievalTaskFields(
            title=seeds.title,
            objective=seeds.objective,
            implementation_steps=seeds.implementation_steps,
            symbols=seeds.symbols,
            akms_tags=seeds.advisory_tags,
        ),
        role=agent_role,
        graph_version=graph_version,
        route_index_hash=route_index_hash,
        resolver_version=resolver_version,
    )


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def fingerprint_resolution_inputs(inputs: ResolutionInputs) -> str:
    """Return the SHA-256 fingerprint of canonical retrieval inputs."""

    if not isinstance(inputs, ResolutionInputs):
        raise TypeError("inputs must be ResolutionInputs")
    payload = inputs.model_dump(mode="json")
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def compute_resolution_fingerprint(
    *,
    task: TaskSeeds | Mapping[str, Any],
    agent_role: AgentRole | str,
    graph_version: str,
    route_index_hash: str,
    changed_paths: Sequence[str] | None = None,
    resolver_version: str = RESOLUTION_RESOLVER_VERSION,
) -> str:
    """Canonicalize current inputs and return their stable fingerprint."""

    inputs = canonicalize_resolution_inputs(
        task=task,
        changed_paths=changed_paths,
        agent_role=agent_role,
        graph_version=graph_version,
        route_index_hash=route_index_hash,
        resolver_version=resolver_version,
    )
    return fingerprint_resolution_inputs(inputs)


def create_resolution_manifest(
    *,
    task: TaskSeeds | Mapping[str, Any],
    resolved_seeds: ResolvedSeeds,
    query_result: TaskKnowledgeQueryResult,
    agent_role: AgentRole | str,
    graph_version: str,
    route_index_hash: str,
    changed_paths: Sequence[str] | None = None,
    resolver_version: str = RESOLUTION_RESOLVER_VERSION,
    generated_at: datetime | str | None = None,
) -> ResolutionManifest:
    """Build a validated manifest from resolver and query results."""

    if not isinstance(query_result, TaskKnowledgeQueryResult):
        raise TypeError("query_result must be TaskKnowledgeQueryResult")
    inputs = canonicalize_resolution_inputs(
        task=task,
        changed_paths=changed_paths,
        agent_role=agent_role,
        graph_version=graph_version,
        route_index_hash=route_index_hash,
        resolver_version=resolver_version,
    )
    selected_nodes = tuple(
        ResolutionSelectedNode(
            node_id=selection.node_id,
            selection_class=selection.selection_class,
            reasons=selection.reasons,
        )
        for selection in query_result.selections
    )
    return ResolutionManifest(
        # The parameter accepts a str for caller convenience; the model field is
        # a tz-aware datetime and pydantic coerces on the way in.
        generated_at=(
            datetime.now(UTC)
            if generated_at is None
            else cast("datetime", generated_at)
        ),
        fingerprint=fingerprint_resolution_inputs(inputs),
        inputs=inputs,
        resolved_seeds=ResolvedSeedsManifest.from_resolved(resolved_seeds),
        selected_nodes=selected_nodes,
    )


def canonical_manifest_bytes(
    manifest: ResolutionManifest | Mapping[str, Any],
) -> bytes:
    """Serialize a manifest as compact, sorted-key UTF-8 JSON."""

    validated = _revalidate_resolution_manifest(manifest)
    return _canonical_json_bytes(validated.model_dump(mode="json"))


def _revalidate_resolution_manifest(
    manifest: ResolutionManifest | Mapping[str, Any],
) -> ResolutionManifest:
    """Force nested model validation at every public consumption boundary."""

    payload = (
        manifest.model_dump(mode="python")
        if isinstance(manifest, ResolutionManifest)
        else manifest
    )
    return ResolutionManifest.model_validate(payload)


def _fsync_parent_directory(directory: Path) -> None:
    """Durably persist a directory entry where the platform supports it."""

    if os.name == "nt":
        return
    unsupported = {
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        directory_descriptor = os.open(directory, flags)
    except OSError as error:
        if error.errno in unsupported:
            return
        raise
    try:
        try:
            os.fsync(directory_descriptor)
        except OSError as error:
            if error.errno not in unsupported:
                raise
    finally:
        os.close(directory_descriptor)


def write_resolution_manifest(
    path: str | Path,
    manifest: ResolutionManifest | Mapping[str, Any],
) -> Path:
    """Atomically replace ``path`` with a complete canonical manifest.

    The temporary file is created in the destination directory, flushed and
    fsynced before :func:`os.replace`, and removed on every failure path. The
    destination directory is fsynced after replacement where supported.
    """

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_manifest_bytes(manifest)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_parent_directory(destination.parent)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return destination


def load_resolution_manifest(path: str | Path) -> ResolutionManifest:
    """Read and validate one manifest from disk."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ResolutionManifest.model_validate(payload)


def validate_resolution_manifest(
    manifest: ResolutionManifest | Mapping[str, Any],
    *,
    task: TaskSeeds | Mapping[str, Any],
    agent_role: AgentRole | str,
    graph_version: str,
    route_index_hash: str,
    changed_paths: Sequence[str] | None = None,
    resolver_version: str = RESOLUTION_RESOLVER_VERSION,
) -> ResolutionManifest:
    """Return ``manifest`` or raise when current retrieval inputs are stale."""

    validated = _revalidate_resolution_manifest(manifest)
    current_fingerprint = compute_resolution_fingerprint(
        task=task,
        changed_paths=changed_paths,
        agent_role=agent_role,
        graph_version=graph_version,
        route_index_hash=route_index_hash,
        resolver_version=resolver_version,
    )
    if validated.fingerprint != current_fingerprint:
        raise StaleResolutionManifestError(
            manifest_fingerprint=validated.fingerprint,
            current_fingerprint=current_fingerprint,
        )
    return validated


def resolution_manifest_is_stale(
    manifest: ResolutionManifest | Mapping[str, Any],
    *,
    task: TaskSeeds | Mapping[str, Any],
    agent_role: AgentRole | str,
    graph_version: str,
    route_index_hash: str,
    changed_paths: Sequence[str] | None = None,
    resolver_version: str = RESOLUTION_RESOLVER_VERSION,
) -> bool:
    """Return whether current retrieval inputs invalidate ``manifest``."""

    try:
        validate_resolution_manifest(
            manifest,
            task=task,
            changed_paths=changed_paths,
            agent_role=agent_role,
            graph_version=graph_version,
            route_index_hash=route_index_hash,
            resolver_version=resolver_version,
        )
    except StaleResolutionManifestError:
        return True
    return False
