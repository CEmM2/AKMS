"""Read-only adapters for importing nodes/edges from the AKMS graph.

**Read-only invariant**: this module NEVER writes to or touches the source
file on disk.  ``load_from_path`` opens the JSON file in read mode only;
file modification timestamps are left unchanged before and after the call.
No function in this module calls ``os.utime``, ``open(..., 'w')``,
``pathlib.Path.touch()``, or any other write operation on the source path.

Public surface::

    GraphSlice           – in-memory container for nodes, edges, metadata
    load_graph           – dispatcher: file-path or in-memory dict
    compute_graph_hash   – deterministic SHA-256 hex digest (sort_keys recipe)
    fixture_graph        – hand-built tiny graph for tests (no disk I/O)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "GraphSlice",
    "load_from_path",
    "load_from_slice",
    "load_graph",
    "compute_graph_hash",
    "fixture_graph",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class GraphSlice(BaseModel):
    """In-memory representation of an AKMS graph slice.

    Fields mirror the top-level structure of a ``graph.json`` produced by the
    AKMS compiler:

    * ``nodes``    – list of node dicts (raw AKMS schema dicts, not typed).
    * ``edges``    – list of edge dicts.
    * ``metadata`` – free-form graph-level metadata (version, build_time, …).

    The model is **frozen** so that equal slices hash identically and can be
    used as dict keys or set members.  ``GraphSlice`` instances are *immutable*
    after construction; mutate by constructing a new instance.
    """

    model_config = ConfigDict(frozen=True)

    nodes: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    edges: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _coerce_list_to_tuple(value: Any) -> tuple[dict[str, Any], ...]:
    """Accept list or tuple; return tuple.  Raises TypeError for anything else."""
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError(f"Expected list or tuple, got {type(value).__name__}")


def _validate_slice_payload(payload: dict[str, Any]) -> GraphSlice:
    """Construct a GraphSlice from a raw dict, coercing list→tuple as needed."""
    nodes = _coerce_list_to_tuple(payload.get("nodes", []))
    edges = _coerce_list_to_tuple(payload.get("edges", []))
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise TypeError(
            f"GraphSlice.metadata must be a dict, got {type(metadata).__name__}"
        )
    return GraphSlice(nodes=nodes, edges=edges, metadata=metadata)


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_from_path(path: str | Path) -> GraphSlice:
    """Load a ``GraphSlice`` from a JSON file on disk.

    The file is opened in **read-only** mode.  File modification timestamps
    are not touched before or after the call.

    Parameters
    ----------
    path:
        Filesystem path to a ``graph.json`` (or equivalent) file.

    Returns
    -------
    GraphSlice
        Validated in-memory representation.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    json.JSONDecodeError
        If the file is not valid JSON.
    TypeError / ValueError
        If the top-level structure does not match the GraphSlice schema.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError(
            f"graph.json must be a JSON object at the top level, got {type(raw).__name__}"
        )
    return _validate_slice_payload(raw)


def load_from_slice(slice_payload: dict[str, Any]) -> GraphSlice:
    """Validate an in-memory dict into a ``GraphSlice``.

    Parameters
    ----------
    slice_payload:
        A dict with optional keys ``nodes``, ``edges``, ``metadata``.

    Returns
    -------
    GraphSlice
    """
    if not isinstance(slice_payload, dict):
        raise TypeError(
            f"slice_payload must be a dict, got {type(slice_payload).__name__}"
        )
    return _validate_slice_payload(slice_payload)


def load_graph(
    graph_path: str | Path | None = None,
    graph_slice: dict[str, Any] | None = None,
) -> GraphSlice:
    """Dispatcher: load a ``GraphSlice`` from exactly one of the two sources.

    Parameters
    ----------
    graph_path:
        If provided, read the graph from this filesystem path.
    graph_slice:
        If provided, validate this in-memory dict into a ``GraphSlice``.

    Returns
    -------
    GraphSlice

    Raises
    ------
    ValueError
        If *both* ``graph_path`` and ``graph_slice`` are provided (mutual
        exclusion), or if *neither* is provided.
    """
    if graph_path is not None and graph_slice is not None:
        raise ValueError(
            "load_graph: 'graph_path' and 'graph_slice' are mutually exclusive — "
            "supply exactly one, not both."
        )
    if graph_path is None and graph_slice is None:
        raise ValueError(
            "load_graph: at least one of 'graph_path' or 'graph_slice' must be provided."
        )
    if graph_path is not None:
        return load_from_path(graph_path)
    return load_from_slice(graph_slice)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------


def compute_graph_hash(graph_slice: GraphSlice) -> str:
    """Return a deterministic SHA-256 hex digest for *graph_slice*.

    The recipe is identical to ``request_hash`` in ``requests.py``:

    1. Build a canonical ``dict`` from the slice (nodes as list, edges as
       list, metadata as dict).
    2. Serialise with ``json.dumps(..., sort_keys=True,
       separators=(',',':'), ensure_ascii=False)``.
    3. Encode as UTF-8.
    4. Return ``hashlib.sha256(...).hexdigest()``.

    The ``sort_keys=True`` flag guarantees that dict key ordering inside
    individual node/edge dicts does NOT affect the digest.

    Parameters
    ----------
    graph_slice:
        A ``GraphSlice`` instance (frozen Pydantic model).

    Returns
    -------
    str
        64-character lowercase hex digest.
    """
    canonical: dict[str, Any] = {
        "edges": list(graph_slice.edges),
        "metadata": graph_slice.metadata,
        "nodes": list(graph_slice.nodes),
    }
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Fixture factory
# ---------------------------------------------------------------------------


def fixture_graph() -> GraphSlice:
    """Return a hand-built ``GraphSlice`` for use in tests and pipeline demos.

    Graph topology (j² return-mapping theme, 6 nodes):

    .. code-block:: text

        prereq_linear_algebra  ──requires──►  core_j2_return_mapping
        prereq_complex_numbers ──requires──►  core_j2_return_mapping
        core_j2_return_mapping ──derives──►   deriv_state_space
        deriv_state_space      ──implements──► impl_pole_placement
        core_j2_return_mapping ──pitfall_of──► pitfall_sign_convention
        impl_pole_placement    ──exercise_for──► exercise_verify_poles

    Edge types used: ``requires``, ``derives``, ``implements``,
    ``pitfall_of``, ``exercise_for``.

    The fixture satisfies the Phase 3 ordering vocabulary (§12) and is
    large enough to be reused as the Phase 4 mode fixture.
    """
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "prereq_linear_algebra",
            "title": "Linear Algebra Foundations",
            "kind": "prerequisite",
            "domain": "mathematics",
            "tags": ["linear_algebra", "matrices", "eigenvalues"],
            "status": "established",
        },
        {
            "node_id": "prereq_complex_numbers",
            "title": "Complex Numbers and the Complex Plane",
            "kind": "prerequisite",
            "domain": "mathematics",
            "tags": ["complex_numbers", "poles", "s_plane"],
            "status": "established",
        },
        {
            "node_id": "core_j2_return_mapping",
            "title": "j² Return Mapping Algorithm",
            "kind": "core_concept",
            "domain": "computational_mechanics",
            "tags": ["j2_plasticity", "return_mapping", "radial_return"],
            "status": "established",
        },
        {
            "node_id": "deriv_state_space",
            "title": "State-Space Form of Elastoplastic Equations",
            "kind": "derivation",
            "domain": "computational_mechanics",
            "tags": ["state_space", "elastoplasticity", "incremental"],
            "status": "tentative",
        },
        {
            "node_id": "impl_pole_placement",
            "title": "Pole Placement Implementation",
            "kind": "implementation",
            "domain": "computational_mechanics",
            "tags": ["pole_placement", "implementation", "python"],
            "status": "tentative",
        },
        {
            "node_id": "pitfall_sign_convention",
            "title": "Sign Convention Pitfall in Stress Update",
            "kind": "pitfall",
            "domain": "computational_mechanics",
            "tags": ["pitfall", "sign_convention", "stress_update"],
            "status": "established",
        },
        {
            "node_id": "exercise_verify_poles",
            "title": "Exercise: Verify Pole Locations Analytically",
            "kind": "exercise",
            "domain": "computational_mechanics",
            "tags": ["exercise", "poles", "verification"],
            "status": "draft",
        },
    ]

    edges: list[dict[str, Any]] = [
        {
            "edge_id": "e_prereq_la_core",
            "from": "prereq_linear_algebra",
            "to": "core_j2_return_mapping",
            "type": "requires",
        },
        {
            "edge_id": "e_prereq_cn_core",
            "from": "prereq_complex_numbers",
            "to": "core_j2_return_mapping",
            "type": "requires",
        },
        {
            "edge_id": "e_core_deriv",
            "from": "core_j2_return_mapping",
            "to": "deriv_state_space",
            "type": "derives",
        },
        {
            "edge_id": "e_deriv_impl",
            "from": "deriv_state_space",
            "to": "impl_pole_placement",
            "type": "implements",
        },
        {
            "edge_id": "e_core_pitfall",
            "from": "core_j2_return_mapping",
            "to": "pitfall_sign_convention",
            "type": "pitfall_of",
        },
        {
            "edge_id": "e_impl_exercise",
            "from": "impl_pole_placement",
            "to": "exercise_verify_poles",
            "type": "exercise_for",
        },
    ]

    metadata: dict[str, Any] = {
        "description": "Minimal fixture graph for j² return-mapping learning path (Phase 3+4 tests)",
        "graph_version": "fixture-v1",
        "node_count": len(nodes),
        "edge_count": len(edges),
    }

    return GraphSlice(
        nodes=tuple(nodes),
        edges=tuple(edges),
        metadata=metadata,
    )
