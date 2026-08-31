"""Parsing and graph-bound validation for task route indexes."""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError
from yaml.nodes import MappingNode

from akms.task_context.models import (
    RouteIndexValidationError,
    RouteValidationIssue,
    TaskRouteIndex,
    normalize_repository_path,
)


class _DuplicateMappingKey(ValueError):
    def __init__(self, key: Any):
        self.key = key
        super().__init__(f"Duplicate mapping key {key!r}")


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that fails rather than dropping duplicate keys."""

    def construct_mapping(
        self,
        node: MappingNode,
        deep: bool = False,
    ) -> dict[Any, Any]:
        if not isinstance(node, MappingNode):
            return super().construct_mapping(node, deep=deep)

        self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError:
                return super().construct_mapping(node, deep=deep)
            if duplicate:
                raise _DuplicateMappingKey(key)
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _json_mapping_without_duplicates(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise _DuplicateMappingKey(key)
        mapping[key] = value
    return mapping


def _location_key(value: Any) -> str | int:
    """Return a stable location component accepted by RouteValidationIssue."""

    if value is None:
        return "<null>"
    if isinstance(value, bool):
        return f"<{str(value).lower()}>"
    if isinstance(value, (str, int)):
        return value
    return repr(value)


def _load_route_source(
    source: Mapping[str, Any] | str | Path,
) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        return source

    path = Path(source)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RouteIndexValidationError(
            [
                RouteValidationIssue(
                    code="route_index_read_error",
                    location=("route_index",),
                    message=f"Could not read route index '{path}': {error}",
                )
            ]
        ) from error

    try:
        if path.suffix.lower() == ".json":
            data = json.loads(
                text,
                object_pairs_hook=_json_mapping_without_duplicates,
            )
        else:
            data = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except _DuplicateMappingKey as error:
        raise RouteIndexValidationError(
            [
                RouteValidationIssue(
                    code="duplicate_mapping_key",
                    location=("route_index", _location_key(error.key)),
                    message=str(error),
                )
            ]
        ) from error
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise RouteIndexValidationError(
            [
                RouteValidationIssue(
                    code="route_index_parse_error",
                    location=("route_index",),
                    message=f"Could not parse route index '{path}': {error}",
                )
            ]
        ) from error

    if not isinstance(data, Mapping):
        raise RouteIndexValidationError(
            [
                RouteValidationIssue(
                    code="schema_validation",
                    location=("route_index",),
                    message="Route index root must be a mapping",
                )
            ]
        )
    return data


def _inspect_raw_routes(data: Mapping[str, Any]) -> list[RouteValidationIssue]:
    issues: list[RouteValidationIssue] = []
    for field in ("by_path", "by_symbol"):
        routes = data.get(field, {} if field == "by_symbol" else None)
        if not isinstance(routes, Mapping):
            continue

        seen_by_route: dict[str, dict[str, tuple[Any, Any]]] = {}
        for raw_key, records in routes.items():
            route_key = raw_key
            if field == "by_path":
                try:
                    route_key = normalize_repository_path(raw_key)
                except (TypeError, ValueError) as error:
                    issues.append(
                        RouteValidationIssue(
                            code="invalid_path",
                            location=(field, _location_key(raw_key)),
                            message=str(error),
                        )
                    )
                    continue
            elif not isinstance(raw_key, str) or not raw_key.strip():
                issues.append(
                    RouteValidationIssue(
                        code="invalid_symbol",
                        location=(field, _location_key(raw_key)),
                        message="Symbol route key must be a non-empty string",
                    )
                )
                continue
            else:
                route_key = raw_key.strip()

            if not isinstance(records, (list, tuple)):
                continue

            seen = seen_by_route.setdefault(route_key, {})
            for index, record in enumerate(records):
                if not isinstance(record, Mapping):
                    continue
                node_id = record.get("node_id")
                if not isinstance(node_id, str) or not node_id.strip():
                    issues.append(
                        RouteValidationIssue(
                            code="missing_node_id",
                            location=(
                                field,
                                _location_key(raw_key),
                                index,
                                "node_id",
                            ),
                            message="Route record must contain a non-empty node_id",
                        )
                    )
                    continue

                node_id = node_id.strip()
                signature = (record.get("reason"), record.get("provenance"))
                previous = seen.get(node_id)
                if previous is None:
                    seen[node_id] = signature
                    continue

                code = (
                    "duplicate_node_record"
                    if previous == signature
                    else "conflicting_node_record"
                )
                description = (
                    "Duplicate" if code == "duplicate_node_record" else "Conflicting"
                )
                issues.append(
                    RouteValidationIssue(
                        code=code,
                        location=(field, _location_key(raw_key), index),
                        message=f"{description} record for node '{node_id}'",
                        node_id=node_id,
                    )
                )
    return issues


def _pydantic_issues(error: ValidationError) -> list[RouteValidationIssue]:
    return [
        RouteValidationIssue(
            code="schema_validation",
            location=tuple(item["loc"]),
            message=item["msg"],
        )
        for item in error.errors(include_url=False)
    ]


def parse_route_index(
    source: TaskRouteIndex | Mapping[str, Any] | str | Path,
    *,
    graph: Any | None = None,
) -> TaskRouteIndex:
    """Parse, canonicalize, and optionally graph-validate a route index."""

    if isinstance(source, TaskRouteIndex):
        index = source
    else:
        data = _load_route_source(source)
        raw_issues = _inspect_raw_routes(data)
        if raw_issues:
            raise RouteIndexValidationError(raw_issues)
        try:
            index = TaskRouteIndex.model_validate(data)
        except ValidationError as error:
            raise RouteIndexValidationError(_pydantic_issues(error)) from error

    if graph is not None:
        validate_route_index_nodes(index, graph)
    return index


def _node_membership(graph: Any) -> Collection[str]:
    if isinstance(graph, (str, bytes, bytearray)):
        raise TypeError("graph must be a node collection, not a string")
    if hasattr(graph, "nodes"):
        nodes = graph.nodes
        # Duck-typed accessor: networkx exposes .nodes as a view, other graph
        # objects as a callable. Neither is statically known here.
        return cast("Collection[str]", nodes() if callable(nodes) else nodes)
    if isinstance(graph, Mapping):
        return graph.keys()
    if isinstance(graph, Collection):
        return graph
    try:
        return frozenset(graph)
    except TypeError as error:
        raise TypeError(
            "graph must expose nodes or be an iterable of node IDs"
        ) from error


def validate_route_index_nodes(
    index: TaskRouteIndex,
    graph: Any,
) -> TaskRouteIndex:
    """Fail closed when a route references a node absent from the graph."""

    nodes = _node_membership(graph)
    issues: list[RouteValidationIssue] = []
    for field in ("by_path", "by_symbol"):
        routes = getattr(index, field)
        for route_key, records in routes.items():
            for record_index, record in enumerate(records):
                if record.node_id not in nodes:
                    issues.append(
                        RouteValidationIssue(
                            code="missing_graph_node",
                            location=(
                                field,
                                route_key,
                                record_index,
                                "node_id",
                            ),
                            message=(
                                "Route references nonexistent graph node "
                                f"'{record.node_id}'"
                            ),
                            node_id=record.node_id,
                        )
                    )
    if issues:
        raise RouteIndexValidationError(issues)
    return index
