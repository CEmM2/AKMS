"""Package-owned deterministic publication validation.

Cross-stream reconciliation deltas (both [package]): fingerprint
reproducibility alone accepted two states a consumer correctly reported as
stale — an unchanged graph carrying a foreign ``repo_id``, and an unchanged
graph containing a fabricated project-namespaced node. Both reproduce
consistently, so ``validate_fingerprint`` said ``current`` while the consumer
said ``stale``. The check now lives in the package (``validate_publication``)
so both consumers inherit one definition instead of mirroring a predicate
that drifts.

Every scenario here stages the frozen consumer-contract pack canonically and
then perturbs ONLY the published artifacts, exactly as an honest user would
encounter them (a graph copied from another project, a graph not rebuilt
after a recompile). The frozen pack itself stages none of these states, so no
pinned expectation moves.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from akms.graph.build_graph import build_graph

from akms_failure_memory.config import load_project_config
from akms_failure_memory.provider import (
    resolve_provider,
    validate_fingerprint,
    validate_publication,
)
from akms_failure_memory.refresh import _finalize_graph_payload

PACK = Path(__file__).resolve().parent / "fixtures/consumer_contract/v1"
CANONICAL_GENERATED_AT = "2026-08-17T00:00:00+00:00"


def _stage(destination: Path) -> tuple[Path, Path]:
    repo = destination / "repo"
    shutil.copytree(PACK, repo)
    vault = destination / "vault"
    vault.mkdir()
    return repo, vault


def _publish_graph(repo: Path, vault: Path) -> Path:
    config = load_project_config(repo / "project.toml")
    output = config.resolve(repo, "graph")
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = output.parent / f".{output.name}.staging"
    build_graph(
        config.resolve(repo, "akms_repo_root"),
        global_vault=vault,
        output_path=scratch,
        strict=True,
    )
    output.write_bytes(
        _finalize_graph_payload(
            json.loads(scratch.read_text(encoding="utf-8")),
            config=config,
            generated_at=CANONICAL_GENERATED_AT,
        )
    )
    scratch.unlink()
    return output


def _rewrite_graph(graph_path: Path, mutate) -> None:
    document = json.loads(graph_path.read_text(encoding="utf-8"))
    mutate(document)
    graph_path.write_text(
        json.dumps(document, sort_keys=True, indent=2), encoding="utf-8"
    )


def _record_then_validate(repo: Path) -> dict:
    """Resolve against the CURRENT published graph, then validate that result.

    The recorded result and the validation see the same unchanged artifacts,
    so the two fingerprints always match; only publication validity can make
    the verdict stale. That is exactly the seam the reconciliation found open.
    """
    recorded = resolve_provider(
        config_path=repo / "project.toml",
        repository_root=repo,
        request_source=repo / "requests/exact-path.json",
    )
    return validate_fingerprint(
        config_path=repo / "project.toml",
        repository_root=repo,
        request_source=repo / "requests/exact-path.json",
        result_path=repo / recorded["artifacts"]["result"],
    )


def _problems(repo: Path) -> list[str]:
    return validate_publication(
        config_path=repo / "project.toml", repository_root=repo
    )


def test_canonical_publication_is_valid_and_current(tmp_path: Path) -> None:
    repo, vault = _stage(tmp_path)
    _publish_graph(repo, vault)
    assert _problems(repo) == []
    verdict = _record_then_validate(repo)
    assert verdict["status"] == "current" and verdict["stale"] is False
    assert verdict["recorded_fingerprint"] == verdict["current_fingerprint"]


def test_foreign_repo_id_refuses_current(tmp_path: Path) -> None:
    """An unchanged graph under a foreign identity is stale, not current."""
    repo, vault = _stage(tmp_path)
    graph_path = _publish_graph(repo, vault)

    def foreign(document: dict) -> None:
        document["graph"]["repo_id"] = "SomeoneElsesRepo"

    _rewrite_graph(graph_path, foreign)
    problems = _problems(repo)
    assert any("repo_id" in problem for problem in problems)
    verdict = _record_then_validate(repo)
    assert verdict["status"] == "stale" and verdict["stale"] is True
    # The seam this closes: the graph never changed between recording and
    # validation, so the fingerprints agree — and the verdict must STILL
    # refuse current, because reproducibility is not identity.
    assert verdict["recorded_fingerprint"] == verdict["current_fingerprint"]


def test_fabricated_project_node_refuses_current(tmp_path: Path) -> None:
    """A project-namespaced graph node with no published file is stale."""
    repo, vault = _stage(tmp_path)
    graph_path = _publish_graph(repo, vault)

    def fabricate(document: dict) -> None:
        node = dict(
            next(n for n in document["nodes"] if n["id"] == "cc-failure-l001")
        )
        node["id"] = "cc-failure-l999"
        document["nodes"].append(node)

    _rewrite_graph(graph_path, fabricate)
    problems = _problems(repo)
    assert any(
        "cc-failure-l999" in problem and "no published generated node file" in problem
        for problem in problems
    )
    verdict = _record_then_validate(repo)
    assert verdict["status"] == "stale" and verdict["stale"] is True
    assert verdict["recorded_fingerprint"] == verdict["current_fingerprint"]


def test_graph_node_content_must_agree_with_published_file(tmp_path: Path) -> None:
    """Resolution reads tags/load_with out of the graph; altered content is stale."""
    repo, vault = _stage(tmp_path)
    graph_path = _publish_graph(repo, vault)

    def alter(document: dict) -> None:
        node = next(n for n in document["nodes"] if n["id"] == "cc-failure-l001")
        node["tags"] = [*node["tags"], "package-doctored"]

    _rewrite_graph(graph_path, alter)
    problems = _problems(repo)
    assert any(
        "cc-failure-l001" in problem and "tags" in problem for problem in problems
    )
    verdict = _record_then_validate(repo)
    assert verdict["status"] == "stale" and verdict["stale"] is True
    assert verdict["recorded_fingerprint"] == verdict["current_fingerprint"]


def test_published_node_missing_from_graph_is_a_problem(tmp_path: Path) -> None:
    """The ordinary case: nodes recompiled, graph not rebuilt.

    Dropping cc-failure-l003 also removes the load_with target that published
    node cc-failure-l002 names, so both problem classes must surface. (The
    resolve path independently fails closed on this state already — route
    validation raises on a route naming a node absent from the graph — so
    only the direct validate_publication verdict is asserted here.)
    """
    repo, vault = _stage(tmp_path)
    graph_path = _publish_graph(repo, vault)

    def drop(document: dict) -> None:
        document["nodes"] = [
            n for n in document["nodes"] if n["id"] != "cc-failure-l003"
        ]

    _rewrite_graph(graph_path, drop)
    problems = _problems(repo)
    assert any(
        "cc-failure-l003" in problem and "missing from the graph" in problem
        for problem in problems
    )
    assert any("load_with target cc-failure-l003" in problem for problem in problems)


def test_unreadable_graph_is_a_problem_not_a_pass(tmp_path: Path) -> None:
    repo, vault = _stage(tmp_path)
    graph_path = _publish_graph(repo, vault)
    graph_path.write_text("{not json", encoding="utf-8")
    problems = _problems(repo)
    assert problems and "unreadable" in problems[0]
