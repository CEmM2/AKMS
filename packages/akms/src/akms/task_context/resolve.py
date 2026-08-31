"""Deterministic task inputs to advisory and exact knowledge seeds.

Exact code-mirror and required-route selection is intentionally independent
from tag derivation: code-mirror nodes are tagless by schema, while required
routes bypass advisory query thresholds and caps.
"""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import networkx as nx

from akms.graph.tag_derivation import derive_tags
from akms.task_context.models import (
    RouteRecord,
    TaskRouteIndex,
    normalize_repository_path,
)
from akms.task_context.routes import parse_route_index

_GLOB_MAGIC = "*?["
_DOCUMENTATION_ROOTS = frozenset({"doc", "docs", "documentation"})
_DOCUMENTATION_SUFFIXES = frozenset({".adoc", ".asciidoc", ".md", ".mdx", ".rst"})


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    values: Sequence[object]
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Sequence):
        values = value
    else:
        return ()
    return tuple(sorted({text for item in values if (text := str(item).strip())}))


@dataclass(frozen=True)
class TaskSeeds:
    """Retrieval-relevant task inputs before graph-bound resolution."""

    scope: tuple[str, ...] = ()
    deliverables: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    advisory_tags: tuple[str, ...] = ()
    title: str = ""
    objective: str = ""
    implementation_steps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "scope",
            "deliverables",
            "changed_files",
            "symbols",
            "advisory_tags",
            "implementation_steps",
        ):
            object.__setattr__(self, name, _text_tuple(getattr(self, name)))
        object.__setattr__(self, "title", str(self.title).strip())
        object.__setattr__(self, "objective", str(self.objective).strip())

    @classmethod
    def from_task(
        cls,
        task: Mapping[str, Any],
        *,
        changed_files: Sequence[str] | None = None,
    ) -> TaskSeeds:
        """Extract retrieval inputs from a task JSON-compatible mapping."""

        task_changed = list(_text_tuple(task.get("changed_files")))
        task_changed.extend(_text_tuple(changed_files))
        return cls(
            scope=_text_tuple(task.get("scope")),
            deliverables=_text_tuple(task.get("deliverables")),
            changed_files=tuple(task_changed),
            symbols=_text_tuple(task.get("symbols")),
            advisory_tags=_text_tuple(task.get("akms_tags")),
            title=str(task.get("title", "")),
            objective=str(task.get("objective", "")),
            implementation_steps=_text_tuple(task.get("implementation_steps")),
        )

    def tag_task(self) -> dict[str, object]:
        """Return the legacy ``derive_tags`` input without changing its API."""

        return {
            "akms_tags": list(self.advisory_tags),
            "scope": list(self.scope),
            "title": self.title,
            "objective": self.objective,
            "implementation_steps": list(self.implementation_steps),
        }


@dataclass(frozen=True)
class ResolvedSeeds:
    """Canonical advisory tags and uncapped exact node seeds."""

    advisory_tags: tuple[str, ...] = ()
    exact_mirror_node_ids: tuple[str, ...] = ()
    required_route_node_ids: tuple[str, ...] = ()
    reasons: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        advisory = _text_tuple(self.advisory_tags)
        mirrors = _text_tuple(self.exact_mirror_node_ids)
        routes = _text_tuple(self.required_route_node_ids)
        selected = set(mirrors) | set(routes)
        reasons = {
            node_id: _text_tuple(node_reasons)
            for node_id, node_reasons in sorted(self.reasons.items())
            if node_id in selected
        }
        missing = sorted(node_id for node_id in selected if not reasons.get(node_id))
        if missing:
            raise ValueError(
                "Every exact seed requires at least one deterministic reason: "
                + ", ".join(missing)
            )
        object.__setattr__(self, "advisory_tags", advisory)
        object.__setattr__(self, "exact_mirror_node_ids", mirrors)
        object.__setattr__(self, "required_route_node_ids", routes)
        object.__setattr__(self, "reasons", reasons)

    @property
    def all_exact_node_ids(self) -> tuple[str, ...]:
        """Return the sorted union of mirror and required-route node IDs."""

        return tuple(
            sorted(set(self.exact_mirror_node_ids) | set(self.required_route_node_ids))
        )


@dataclass(frozen=True)
class TaskPathSpec:
    """One canonical repository path input used by task resolution."""

    value: str
    kind: Literal["exact", "directory", "glob"]
    source: Literal["scope", "deliverable", "changed_file"]

    def matches(self, repository_path: str) -> bool:
        if self.kind == "exact":
            return repository_path == self.value
        if self.kind == "directory":
            return repository_path.startswith(f"{self.value}/")
        return _glob_matches(repository_path, self.value)


def _glob_matches(repository_path: str, pattern: str) -> bool:
    """Match POSIX path segments with ``**`` as zero-or-more segments."""

    path_parts = repository_path.split("/")
    pattern_parts = pattern.split("/")

    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        pattern_part = pattern_parts[pattern_index]
        if pattern_part == "**":
            return match(path_index, pattern_index + 1) or (
                path_index < len(path_parts) and match(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatch.fnmatchcase(path_parts[path_index], pattern_part)
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)


def _looks_like_path(value: str) -> bool:
    """Reject human-readable deliverables while accepting explicit paths."""

    return not any(char.isspace() for char in value) and (
        "/" in value
        or "\\" in value
        or any(char in value for char in _GLOB_MAGIC)
        or bool(PurePosixPath(value).suffix)
    )


#: Which seed field a path spec was derived from.
_PathSpecSource = Literal["scope", "deliverable", "changed_file"]


def _path_spec(
    raw_value: str,
    *,
    source: _PathSpecSource,
) -> TaskPathSpec | None:
    value = raw_value.strip()
    if not value or (source == "deliverable" and not _looks_like_path(value)):
        return None

    normalized_separators = value.replace("\\", "/")
    if source == "changed_file":
        kind: Literal["exact", "directory", "glob"] = "exact"
    elif any(char in normalized_separators for char in _GLOB_MAGIC):
        kind = "glob"
    elif normalized_separators.endswith("/"):
        kind = "directory"
    else:
        kind = "exact"

    try:
        normalized = normalize_repository_path(normalized_separators)
    except (TypeError, ValueError):
        return None
    return TaskPathSpec(value=normalized, kind=kind, source=source)


def canonicalize_task_path_specs(seeds: TaskSeeds) -> tuple[TaskPathSpec, ...]:
    """Return normalized, filtered path specs exactly as resolution consumes."""

    if not isinstance(seeds, TaskSeeds):
        raise TypeError("seeds must be TaskSeeds")
    specs: set[TaskPathSpec] = set()
    sources: tuple[tuple[_PathSpecSource, Iterable[str]], ...] = (
        ("scope", seeds.scope),
        ("deliverable", seeds.deliverables),
        ("changed_file", seeds.changed_files),
    )
    for source, values in sources:
        for value in values:
            spec = _path_spec(value, source=source)
            if spec is not None:
                specs.add(spec)
    return tuple(sorted(specs, key=lambda spec: (spec.source, spec.kind, spec.value)))


def _is_documentation_path(spec: TaskPathSpec) -> bool:
    path = spec.value.casefold()
    parts = path.split("/")
    basename = parts[-1]
    return (
        parts[0] in _DOCUMENTATION_ROOTS
        or basename.startswith("readme")
        or PurePosixPath(path).suffix in _DOCUMENTATION_SUFFIXES
    )


def _is_documentation_only(
    seeds: TaskSeeds,
    specs: Sequence[TaskPathSpec],
) -> bool:
    """Return true when every exact-path input is documentation."""

    return (
        bool(specs)
        and not seeds.symbols
        and all(_is_documentation_path(spec) for spec in specs)
    )


def _is_code_mirror(data: Mapping[str, Any]) -> bool:
    return (
        data.get("domain") == "code-mirror" or data.get("node_origin") == "code-mirror"
    )


def _match_reason(
    *,
    subject: str,
    repository_path: str,
    spec: TaskPathSpec,
) -> str:
    return (
        f"{subject} '{repository_path}' matched {spec.kind} "
        f"{spec.source} '{spec.value}'"
    )


def _route_provenance(record: RouteRecord) -> str:
    if isinstance(record.provenance, str):
        return record.provenance
    return json.dumps(
        record.provenance,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def resolve_task_seeds(
    graph: nx.DiGraph,
    seeds: TaskSeeds | Mapping[str, Any],
    *,
    route_index: TaskRouteIndex | Mapping[str, Any] | str | Path | None = None,
    changed_files: Sequence[str] | None = None,
) -> ResolvedSeeds:
    """Resolve advisory tags, exact mirror IDs, route IDs, and reasons.

    Plain paths match exactly. A trailing slash declares a directory input and
    glob metacharacters declare a glob input. ``changed_files`` are always
    exact paths, even if a filename contains glob metacharacters.
    """

    if isinstance(seeds, Mapping):
        task_seeds = TaskSeeds.from_task(seeds, changed_files=changed_files)
    elif isinstance(seeds, TaskSeeds):
        if changed_files:
            task_seeds = TaskSeeds(
                scope=seeds.scope,
                deliverables=seeds.deliverables,
                changed_files=seeds.changed_files + tuple(changed_files),
                symbols=seeds.symbols,
                advisory_tags=seeds.advisory_tags,
                title=seeds.title,
                objective=seeds.objective,
                implementation_steps=seeds.implementation_steps,
            )
        else:
            task_seeds = seeds
    else:
        raise TypeError("seeds must be TaskSeeds or a task mapping")

    specs = canonicalize_task_path_specs(task_seeds)
    if _is_documentation_only(task_seeds, specs):
        specs = ()
    reasons: dict[str, set[str]] = {}
    mirror_ids: set[str] = set()
    route_ids: set[str] = set()

    for node_id, data in graph.nodes(data=True):
        if not _is_code_mirror(data):
            continue
        source_file = data.get("source_file")
        if not isinstance(source_file, str):
            continue
        try:
            repository_path = normalize_repository_path(source_file)
        except ValueError:
            continue
        for spec in specs:
            if spec.matches(repository_path):
                node_key = str(node_id)
                mirror_ids.add(node_key)
                reasons.setdefault(node_key, set()).add(
                    _match_reason(
                        subject="mirror source_file",
                        repository_path=repository_path,
                        spec=spec,
                    )
                )

    if route_index is not None:
        index = parse_route_index(route_index, graph=graph)
        for repository_path, records in index.by_path.items():
            for spec in specs:
                if not spec.matches(repository_path):
                    continue
                for record in records:
                    route_ids.add(record.node_id)
                    reasons.setdefault(record.node_id, set()).add(
                        (
                            _match_reason(
                                subject="required route",
                                repository_path=repository_path,
                                spec=spec,
                            )
                            + f": {record.reason}"
                            + f" [provenance={_route_provenance(record)}]"
                        )
                    )
        for symbol in task_seeds.symbols:
            for record in index.by_symbol.get(symbol, ()):
                route_ids.add(record.node_id)
                reasons.setdefault(record.node_id, set()).add(
                    f"required symbol route '{symbol}': {record.reason} "
                    f"[provenance={_route_provenance(record)}]"
                )

    advisory_tags = tuple(sorted(set(derive_tags(graph, task_seeds.tag_task()))))
    return ResolvedSeeds(
        advisory_tags=advisory_tags,
        exact_mirror_node_ids=tuple(mirror_ids),
        required_route_node_ids=tuple(route_ids),
        reasons={
            node_id: tuple(node_reasons) for node_id, node_reasons in reasons.items()
        },
    )
