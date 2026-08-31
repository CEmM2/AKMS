"""Tests for deterministic task-knowledge resolution manifests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from akms.schema.models import AgentRole
from akms.task_context.manifest import (
    RESOLUTION_RESOLVER_VERSION,
    ResolutionManifest,
    ResolutionSelectedNode,
    StaleResolutionManifestError,
    canonical_manifest_bytes,
    compute_resolution_fingerprint,
    create_resolution_manifest,
    load_resolution_manifest,
    validate_resolution_manifest,
    write_resolution_manifest,
)
from akms.task_context.query import (
    NodeSelection,
    SelectionClass,
    TaskKnowledgeQueryResult,
)
from akms.task_context.resolve import ResolvedSeeds, TaskSeeds

_GENERATED_AT = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
_GOLDEN_MANIFEST_WITHOUT_TIMESTAMP = (
    b"""{"fingerprint":"4fcbb80800d6169511402836742fc4329a8380e4609a54da25cacbd30c85cffe","""
    b""""inputs":{"changed_paths":[{"kind":"exact","value":"src/changed_b.py"},"""
    b"""{"kind":"exact","value":"src/uncommitted.py"}],"""
    b""""declared_paths":{"deliverables":[{"kind":"exact","value":"src/output.json"}],"""
    b""""scope":[{"kind":"exact","value":"src/a.py"},"""
    b"""{"kind":"exact","value":"src/z.py"}]},"graph_version":"graph-sha256","""
    b""""resolver_version":"task-knowledge-resolver-v1","role":"implementer","""
    b""""route_index_hash":"route-sha256","task_fields":{"akms_tags":["determinism","manifest"],"""
    b""""implementation_steps":["Hash retrieval inputs","Write atomically"],"""
    b""""objective":"Record retrieval inputs and selected nodes.","""
    b""""symbols":["resolve_a","resolve_z"],"""
    b""""title":"Generate a deterministic resolution manifest"}},"""
    b""""resolved_seeds":{"advisory_tags":["determinism","manifest"],"""
    b""""exact_mirror_node_ids":["mirror-a"],"""
    b""""reasons":{"mirror-a":["exact mirror path"],"required-a":["required route path"]},"""
    b""""required_route_node_ids":["required-a"]},"schema_version":"v1","""
    b""""selected_nodes":[{"node_id":"mirror-a","reasons":["exact mirror path"],"""
    b""""selection_class":"required"},{"node_id":"required-a","""
    b""""reasons":["required route path"],"selection_class":"required"},"""
    b"""{"node_id":"companion-a","reasons":["load_with from required node 'required-a'"],"""
    b""""selection_class":"coactivated"},{"node_id":"advisory-a","""
    b""""reasons":["advisory tag query: determinism, manifest"],"""
    b""""selection_class":"advisory"}]}"""
)


def _task() -> dict[str, object]:
    return {
        "task_id": "TASK-042",
        "title": "Generate a deterministic resolution manifest",
        "objective": "Record retrieval inputs and selected nodes.",
        "scope": ["src/z.py", "src/a.py", "src/a.py"],
        "deliverables": ["src/output.json", "Resolution manifest model"],
        "implementation_steps": ["Write atomically", "Hash retrieval inputs"],
        "symbols": ["resolve_z", "resolve_a"],
        "akms_tags": ["manifest", "determinism"],
        "changed_files": ["src/changed_b.py"],
        "status": "in_progress",
        "completion_date": "",
        "routing_evidence": [{"purpose": "implementer", "volatile": True}],
        "review_score": 0,
    }


def _resolved() -> ResolvedSeeds:
    return ResolvedSeeds(
        advisory_tags=("manifest", "determinism"),
        exact_mirror_node_ids=("mirror-a",),
        required_route_node_ids=("required-a",),
        reasons={
            "mirror-a": ("exact mirror path",),
            "required-a": ("required route path",),
        },
    )


def _query_result() -> TaskKnowledgeQueryResult:
    return TaskKnowledgeQueryResult(
        selections=(
            NodeSelection(
                node_id="mirror-a",
                selection_class=SelectionClass.REQUIRED,
                node_data={"title": "Mirror A"},
                reasons=("exact mirror path",),
            ),
            NodeSelection(
                node_id="required-a",
                selection_class=SelectionClass.REQUIRED,
                node_data={"title": "Required A"},
                reasons=("required route path",),
            ),
            NodeSelection(
                node_id="companion-a",
                selection_class=SelectionClass.COACTIVATED,
                node_data={"title": "Companion A"},
                reasons=("load_with from required node 'required-a'",),
            ),
            NodeSelection(
                node_id="advisory-a",
                selection_class=SelectionClass.ADVISORY,
                node_data={"title": "Advisory A"},
                reasons=("advisory tag query: determinism, manifest",),
            ),
        )
    )


def _manifest(
    *,
    task: dict[str, object] | TaskSeeds | None = None,
    query_result: TaskKnowledgeQueryResult | None = None,
    changed_paths: tuple[str, ...] = ("src/uncommitted.py",),
    agent_role: AgentRole | str = AgentRole.IMPLEMENTER,
    graph_version: str = "graph-sha256",
    route_index_hash: str = "route-sha256",
    resolver_version: str = RESOLUTION_RESOLVER_VERSION,
    generated_at: datetime = _GENERATED_AT,
) -> ResolutionManifest:
    return create_resolution_manifest(
        task=_task() if task is None else task,
        changed_paths=changed_paths,
        agent_role=agent_role,
        graph_version=graph_version,
        route_index_hash=route_index_hash,
        resolver_version=resolver_version,
        resolved_seeds=_resolved(),
        query_result=_query_result() if query_result is None else query_result,
        generated_at=generated_at,
    )


@pytest.mark.unit
def test_golden_manifest_serialization_is_deterministic() -> None:
    first = _manifest()
    reordered_task = _task()
    for field in (
        "scope",
        "deliverables",
        "implementation_steps",
        "symbols",
        "akms_tags",
    ):
        reordered_task[field] = list(reversed(reordered_task[field]))  # type: ignore[arg-type]

    second = _manifest(task=reordered_task)

    assert first == second
    first_bytes = canonical_manifest_bytes(first)
    assert first_bytes == canonical_manifest_bytes(second)
    without_timestamp = first_bytes.replace(
        b'"generated_at":"2026-07-26T12:00:00Z",',
        b"",
    )
    assert without_timestamp == _GOLDEN_MANIFEST_WITHOUT_TIMESTAMP
    payload = json.loads(first_bytes)
    assert list(payload) == sorted(payload)
    assert payload["inputs"]["declared_paths"] == {
        "deliverables": [{"kind": "exact", "value": "src/output.json"}],
        "scope": [
            {"kind": "exact", "value": "src/a.py"},
            {"kind": "exact", "value": "src/z.py"},
        ],
    }
    assert payload["inputs"]["changed_paths"] == [
        {"kind": "exact", "value": "src/changed_b.py"},
        {"kind": "exact", "value": "src/uncommitted.py"},
    ]
    assert payload["selected_nodes"] == [
        {
            "node_id": "mirror-a",
            "reasons": ["exact mirror path"],
            "selection_class": "required",
        },
        {
            "node_id": "required-a",
            "reasons": ["required route path"],
            "selection_class": "required",
        },
        {
            "node_id": "companion-a",
            "reasons": ["load_with from required node 'required-a'"],
            "selection_class": "coactivated",
        },
        {
            "node_id": "advisory-a",
            "reasons": ["advisory tag query: determinism, manifest"],
            "selection_class": "advisory",
        },
    ]


@pytest.mark.unit
def test_selected_nodes_are_canonical_within_each_class() -> None:
    canonical_result = _query_result()
    reversed_required = TaskKnowledgeQueryResult(
        selections=(
            canonical_result.selections[1],
            canonical_result.selections[0],
            *canonical_result.selections[2:],
        )
    )

    canonical = _manifest(query_result=canonical_result)
    reordered = _manifest(query_result=reversed_required)

    assert canonical == reordered
    assert canonical_manifest_bytes(canonical) == canonical_manifest_bytes(reordered)
    assert tuple(selection.node_id for selection in reordered.selected_nodes) == (
        "mirror-a",
        "required-a",
        "companion-a",
        "advisory-a",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("scope", ["src/different.py"]),
        ("deliverables", ["src/different.json"]),
        ("symbols", ["different_symbol"]),
        ("akms_tags", ["different-tag"]),
        ("title", "Different title"),
        ("objective", "Different objective"),
        ("implementation_steps", ["Different step"]),
    ],
)
def test_each_retrieval_task_field_changes_fingerprint(
    field: str,
    replacement: object,
) -> None:
    task = _task()
    task[field] = replacement

    assert _manifest(task=task).fingerprint != _manifest().fingerprint


@pytest.mark.unit
@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("changed_paths", ("src/other.py",)),
        ("agent_role", AgentRole.CODE_REVIEWER),
        ("graph_version", "other-graph"),
        ("route_index_hash", "other-route-index"),
        ("resolver_version", "other-resolver"),
    ],
)
def test_each_non_task_retrieval_input_changes_fingerprint(
    override: str,
    value: object,
) -> None:
    baseline = _manifest()
    kwargs = {override: value}

    assert _manifest(**kwargs).fingerprint != baseline.fingerprint  # type: ignore[arg-type]


@pytest.mark.unit
def test_separator_equivalent_paths_have_the_same_fingerprint() -> None:
    posix_task = _task()
    windows_task = _task()
    windows_task["scope"] = [r"src\z.py", r"src\a.py"]
    windows_task["deliverables"] = [
        r"src\output.json",
        "Different human-readable prose",
    ]
    windows_task["changed_files"] = [r"src\changed_b.py"]

    windows = _manifest(
        task=windows_task,
        changed_paths=(r"src\uncommitted.py",),
    )
    assert windows.fingerprint == _manifest(task=posix_task).fingerprint


@pytest.mark.unit
def test_irrelevant_or_invalid_deliverables_do_not_change_fingerprint() -> None:
    baseline_task = _task()
    noisy_task = _task()
    noisy_task["deliverables"] = [
        "src/output.json",
        "Different human-readable prose",
        "../outside-repository.json",
    ]

    assert (
        _manifest(task=noisy_task).fingerprint
        == _manifest(task=baseline_task).fingerprint
    )


@pytest.mark.unit
def test_changed_files_are_normalized_and_remain_exact_specs() -> None:
    task = _task()
    task["changed_files"] = [r"src\literal[1].py"]
    manifest = _manifest(
        task=task,
        changed_paths=(r"src\literal*.py",),
    )

    assert manifest.inputs.model_dump(mode="json")["changed_paths"] == [
        {"kind": "exact", "value": "src/literal*.py"},
        {"kind": "exact", "value": "src/literal[1].py"},
    ]


@pytest.mark.unit
def test_generated_at_is_isolated_from_fingerprint() -> None:
    first = _manifest(generated_at=_GENERATED_AT)
    second = _manifest(
        generated_at=datetime(2030, 1, 1, 1, 2, 3, tzinfo=UTC),
    )

    assert first.generated_at != second.generated_at
    assert first.fingerprint == second.fingerprint
    first_payload = first.model_dump(mode="json")
    second_payload = second.model_dump(mode="json")
    first_payload.pop("generated_at")
    second_payload.pop("generated_at")
    assert first_payload == second_payload


@pytest.mark.unit
def test_unrelated_task_metadata_does_not_invalidate_fingerprint() -> None:
    changed_metadata = _task()
    changed_metadata.update(
        {
            "status": "complete",
            "completion_date": "2030-01-01",
            "routing_evidence": [{"purpose": "reviewer", "volatile": "different"}],
            "review_score": 10,
            "test_completion": {"passed": 999, "total": 999},
            "completion_notes": ["unrelated"],
        }
    )

    assert _manifest(task=changed_metadata).fingerprint == _manifest().fingerprint


@pytest.mark.unit
def test_compute_fingerprint_accepts_canonical_task_seeds() -> None:
    task = _task()
    from_mapping = compute_resolution_fingerprint(
        task=task,
        changed_paths=("src/uncommitted.py",),
        agent_role=AgentRole.IMPLEMENTER,
        graph_version="graph-sha256",
        route_index_hash="route-sha256",
    )
    from_seeds = compute_resolution_fingerprint(
        task=TaskSeeds.from_task(
            task,
            changed_files=("src/uncommitted.py",),
        ),
        agent_role=AgentRole.IMPLEMENTER,
        graph_version="graph-sha256",
        route_index_hash="route-sha256",
    )

    assert from_mapping == from_seeds


@pytest.mark.unit
def test_changed_paths_boundary_has_mapping_and_task_seeds_parity() -> None:
    task = _task()
    seeds = TaskSeeds.from_task(task)
    common = {
        "agent_role": AgentRole.IMPLEMENTER,
        "graph_version": "graph-sha256",
        "route_index_hash": "route-sha256",
    }

    from_mapping = compute_resolution_fingerprint(
        task=task,
        changed_paths=("src/a.py",),
        **common,
    )
    from_seeds = compute_resolution_fingerprint(
        task=seeds,
        changed_paths=("src/a.py",),
        **common,
    )
    assert from_mapping == from_seeds

    for task_input in (task, seeds):
        for scalar in ("src/a.py", b"src/a.py"):
            with pytest.raises(TypeError, match="changed_paths"):
                compute_resolution_fingerprint(
                    task=task_input,
                    changed_paths=scalar,  # type: ignore[arg-type]
                    **common,
                )


@pytest.mark.unit
def test_stale_validation_checks_current_retrieval_inputs() -> None:
    manifest = _manifest()
    current = {
        "task": _task(),
        "changed_paths": ("src/uncommitted.py",),
        "agent_role": AgentRole.IMPLEMENTER,
        "graph_version": "graph-sha256",
        "route_index_hash": "route-sha256",
        "resolver_version": RESOLUTION_RESOLVER_VERSION,
    }

    assert validate_resolution_manifest(manifest, **current) == manifest

    current["graph_version"] = "new-graph-version"
    with pytest.raises(StaleResolutionManifestError) as exc_info:
        validate_resolution_manifest(manifest, **current)

    assert exc_info.value.manifest_fingerprint == manifest.fingerprint
    assert exc_info.value.current_fingerprint != manifest.fingerprint


@pytest.mark.unit
def test_selected_nodes_require_class_and_reasons() -> None:
    with pytest.raises(ValidationError):
        ResolutionSelectedNode.model_validate(
            {"node_id": "missing-class", "reasons": ["reason"]}
        )
    with pytest.raises(ValidationError):
        ResolutionSelectedNode(
            node_id="missing-reasons",
            selection_class=SelectionClass.REQUIRED,
            reasons=(),
        )


@pytest.mark.unit
def test_manifest_rejects_missing_or_misclassified_exact_selections() -> None:
    payload = _manifest().model_dump(mode="json")
    del payload["selected_nodes"][0]

    with pytest.raises(ValidationError, match="exact resolved nodes"):
        ResolutionManifest.model_validate(payload)


@pytest.mark.unit
def test_manifest_rejects_required_selection_reason_drift() -> None:
    payload = _manifest().model_dump(mode="json")
    payload["selected_nodes"][0]["reasons"] = ["contradictory reason"]

    with pytest.raises(ValidationError, match="reasons"):
        ResolutionManifest.model_validate(payload)


@pytest.mark.unit
def test_nested_reason_mutation_is_blocked_and_revalidated() -> None:
    manifest = _manifest()

    with pytest.raises(TypeError):
        manifest.resolved_seeds.reasons["mirror-a"] = ("tampered",)

    object.__setattr__(
        manifest.resolved_seeds,
        "reasons",
        {
            "mirror-a": ("tampered",),
            "required-a": ("required route path",),
        },
    )

    with pytest.raises(ValidationError, match="reasons"):
        canonical_manifest_bytes(manifest)
    with pytest.raises(ValidationError, match="reasons"):
        validate_resolution_manifest(
            manifest,
            task=_task(),
            changed_paths=("src/uncommitted.py",),
            agent_role=AgentRole.IMPLEMENTER,
            graph_version="graph-sha256",
            route_index_hash="route-sha256",
        )


@pytest.mark.unit
def test_atomic_writer_exposes_only_complete_old_or_new_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "resolution.json"
    old_manifest = _manifest()
    new_manifest = _manifest(graph_version="new-graph")
    write_resolution_manifest(destination, old_manifest)

    observed: list[dict[str, object]] = []
    from akms.task_context import manifest as manifest_module

    real_replace = manifest_module.os.replace

    def observing_replace(source: str | Path, target: str | Path) -> None:
        observed.append(json.loads(Path(target).read_bytes()))
        real_replace(source, target)
        observed.append(json.loads(Path(target).read_bytes()))

    monkeypatch.setattr(manifest_module.os, "replace", observing_replace)
    write_resolution_manifest(destination, new_manifest)

    assert [item["fingerprint"] for item in observed] == [
        old_manifest.fingerprint,
        new_manifest.fingerprint,
    ]
    assert load_resolution_manifest(destination) == new_manifest
    assert not list(tmp_path.glob(".resolution.json.*.tmp"))


@pytest.mark.unit
def test_atomic_writer_fsyncs_parent_after_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "resolution.json"
    from akms.task_context import manifest as manifest_module

    events: list[tuple[str, Path]] = []
    real_replace = manifest_module.os.replace

    def observing_replace(source: str | Path, target: str | Path) -> None:
        real_replace(source, target)
        events.append(("replace", Path(target)))

    def observing_parent_fsync(directory: Path) -> None:
        assert destination.exists()
        events.append(("parent-fsync", directory))

    monkeypatch.setattr(manifest_module.os, "replace", observing_replace)
    monkeypatch.setattr(
        manifest_module,
        "_fsync_parent_directory",
        observing_parent_fsync,
        raising=False,
    )

    write_resolution_manifest(destination, _manifest())

    assert events == [
        ("replace", destination),
        ("parent-fsync", tmp_path),
    ]


@pytest.mark.unit
def test_atomic_writer_cleans_temporary_file_after_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "resolution.json"
    from akms.task_context import manifest as manifest_module

    def failing_replace(source: str | Path, target: str | Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(manifest_module.os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        write_resolution_manifest(destination, _manifest())

    assert not destination.exists()
    assert not list(tmp_path.glob(".resolution.json.*.tmp"))
