from __future__ import annotations

import json
from pathlib import Path

import yaml

from akms_nodes_gen import nlm_batch


def _write_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "plan": "Example Plan",
                "nlm": {"notebook_id": "nb-example"},
                "clusters": [
                    {
                        "cluster": "B1",
                        "name": "Batch One",
                        "nodes": [
                            {
                                "id": "node-a",
                                "title": "Node A",
                                "source": "Smith Eq. 1",
                                "status": "new",
                            },
                            {
                                "id": "node-b",
                                "title": "Node B",
                                "source": "Jones Section 2",
                                "status": "new",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_load_batch_uses_plan_notebook_and_selected_cluster(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)

    batch = nlm_batch.load_batch(plan_path, batch_id="B1", notebook_id=None)

    assert batch.notebook_id == "nb-example"
    assert batch.batch_id == "B1"
    assert [node.id for node in batch.nodes] == ["node-a", "node-b"]


def test_parse_structured_response_extracts_fenced_yaml() -> None:
    response = """Here is the node:

```yaml
id: node-a
title: "Node A"
domain: computational-mechanics
tags: [fem]
status: tentative
confidence: 0.90
source: hybrid
edges:
  - to: node-b
    type: requires
    weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
summary: |
  Summary with source ref [Smith 2020].
core_concept: |
  Concept.
math_formulation:
  equations:
    - label: governing
      latex: x = y
      source_ref: Smith 2020 Eq. 1
algorithms:
  - label: update
    source_ref: Smith 2020 Algorithm 1
    steps:
      - cmd: State
        math: x \\gets y
pitfalls:
  - name: pitfall
    description: supported issue
    source_ref: Smith 2020 p. 3
references:
  - Smith 2020
```
"""

    parsed = nlm_batch.parse_structured_response(response, output_format="yaml")

    assert parsed["id"] == "node-a"
    assert (
        parsed["math_formulation"]["equations"][0]["source_ref"] == "Smith 2020 Eq. 1"
    )


def test_parse_structured_response_repairs_latex_yaml_escapes() -> None:
    response = r"""```yaml
id: node-a
summary: "Balance f^{\mathrm{ext}} against f^{\mathrm{int}} with \phi."
math_formulation:
  equations:
    - label: residual
      latex: "r = f^{\mathrm{ext}} - f^{\mathrm{int}}"
```
"""

    parsed = nlm_batch.parse_structured_response(response, output_format="yaml")

    assert parsed["summary"] == (
        r"Balance f^{\mathrm{ext}} against f^{\mathrm{int}} with \phi."
    )
    assert parsed["math_formulation"]["equations"][0]["latex"] == (
        r"r = f^{\mathrm{ext}} - f^{\mathrm{int}}"
    )


def test_parse_structured_response_quotes_flow_style_latex_keys() -> None:
    response = r"""```yaml
id: node-a
math_formulation:
  notation:
    [D^{\mathrm{e}}]: 'elastic material matrix'
```
"""

    parsed = nlm_batch.parse_structured_response(response, output_format="yaml")

    assert parsed["math_formulation"]["notation"] == {
        r"[D^{\mathrm{e}}]": "elastic material matrix"
    }


def test_parse_structured_response_quotes_plain_values_with_colons() -> None:
    response = r"""```yaml
id: node-a
core_concept: Update the solution in two phases: first predict, then correct.
pitfalls:
  - name: breakdown
    description: Failure has two stages: loss of orthogonality, then stagnation.
```
"""

    parsed = nlm_batch.parse_structured_response(response, output_format="yaml")

    assert parsed["core_concept"] == (
        "Update the solution in two phases: first predict, then correct."
    )
    assert parsed["pitfalls"][0]["description"] == (
        "Failure has two stages: loss of orthogonality, then stagnation."
    )


def test_validate_node_requires_grounding_and_known_edges() -> None:
    node = {
        "id": "node-a",
        "title": "Node A",
        "domain": "computational-mechanics",
        "tags": ["fem"],
        "status": "tentative",
        "confidence": 0.90,
        "source": "hybrid",
        "edges": [{"to": "missing-node", "type": "requires", "weight": 1.0}],
        "context_size": "medium",
        "reading_priority": "full",
        "content_ref": None,
        "akms_schema": "v2",
        "summary": "summary",
        "core_concept": "concept",
        "math_formulation": {
            "equations": [{"label": "governing", "latex": "x = y"}],
        },
        "algorithms": [
            {"label": "update", "steps": [{"cmd": "State", "math": "x \\gets y"}]}
        ],
        "pitfalls": [{"name": "pitfall", "description": "desc"}],
    }

    errors = nlm_batch.validate_node_data(
        node,
        spec=nlm_batch.NodeRequest(
            id="node-a", title="Node A", source="Smith Eq. 1", status="new"
        ),
        known_edge_targets={"node-b"},
        require_source_refs=True,
    )

    assert any("Unknown edge target" in error for error in errors)
    assert any("source_ref" in error for error in errors)


def test_apply_plan_owned_metadata_is_explicitly_gated() -> None:
    generated = {
        "id": "paraphrased-id",
        "title": "Paraphrased title",
        "domain": "wrong-domain",
        "tags": ["wrong-tag"],
        "status": "established",
        "confidence": 0.2,
        "source": "agent",
        "edges": [{"to": "node-b", "type": "requires"}],
        "reading_priority": None,
        "content_ref": "external.md",
        "akms_schema": "v1",
        "summary": "source-grounded generated content",
    }
    unlocked = nlm_batch.NodeRequest(id="node-a", title="Node A", hint="ordinary hint")
    assert nlm_batch._apply_plan_owned_metadata(generated, unlocked) is generated

    locked = nlm_batch.NodeRequest(
        id="node-a",
        title="Node A",
        hint=json.dumps(
            {
                "lock_plan_metadata": True,
                "identity": {
                    "domain": "computational-mechanics",
                    "subdomain": "plasticity",
                    "tags": ["plasticity"],
                    "edges": [
                        {"to": "node-b", "type": "requires"},
                        {"to": "node-c", "type": "refines"},
                    ],
                    "reading_priority": "full",
                },
            }
        ),
    )
    normalized = nlm_batch._apply_plan_owned_metadata(generated, locked)

    assert normalized["id"] == "node-a"
    assert normalized["title"] == "Node A"
    assert normalized["domain"] == "computational-mechanics"
    assert normalized["subdomain"] == "plasticity"
    assert normalized["tags"] == ["plasticity"]
    assert normalized["edges"] == [
        {"to": "node-b", "type": "requires", "weight": 1.0},
        {"to": "node-c", "type": "refines", "weight": 0.7},
    ]
    assert normalized["reading_priority"] == "full"
    assert normalized["status"] == "tentative"
    assert normalized["confidence"] == 0.90
    assert normalized["source"] == "hybrid"
    assert normalized["content_ref"] is None
    assert normalized["akms_schema"] == "v2"
    assert normalized["summary"] == generated["summary"]


def test_run_batch_processes_nodes_serially_and_writes_state(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Generate the node as {output_format}.", encoding="utf-8")
    template_path = tmp_path / "template.yaml"
    template_path.write_text("id: <id>\ntitle: <title>\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    calls: list[str] = []

    def fake_query(question: str, options: nlm_batch.QueryOptions) -> str:
        calls.append(question)
        node_id = "node-a" if len(calls) == 1 else "node-b"
        title = "Node A" if len(calls) == 1 else "Node B"
        payload = {
            "id": node_id,
            "title": title,
            "domain": "computational-mechanics",
            "tags": ["fem"],
            "status": "tentative",
            "confidence": 0.90,
            "source": "hybrid",
            "edges": [
                {
                    "to": "node-b" if node_id == "node-a" else "node-a",
                    "type": "requires",
                    "weight": 1.0,
                }
            ],
            "context_size": "medium",
            "reading_priority": "full",
            "content_ref": None,
            "akms_schema": "v2",
            "summary": "summary [Smith 2020]",
            "core_concept": "concept [Smith 2020]",
            "math_formulation": {
                "equations": [
                    {"label": "governing", "latex": "x = y", "source_ref": "Smith 2020"}
                ]
            },
            "algorithms": [
                {
                    "label": "update",
                    "source_ref": "Smith 2020",
                    "steps": [{"cmd": "State", "math": "x \\gets y"}],
                }
            ],
            "pitfalls": [
                {"name": "pitfall", "description": "desc", "source_ref": "Smith 2020"}
            ],
            "references": ["Smith 2020"],
        }
        return "```yaml\n" + yaml.safe_dump(payload, sort_keys=False) + "```"

    result = nlm_batch.run_batch(
        nlm_batch.BatchRunConfig(
            plan_path=plan_path,
            out_dir=out_dir,
            prompt_file=prompt_path,
            template_file=template_path,
            output_format="yaml",
            timeout=30.0,
            source_ids=["source-1"],
            batch_id="B1",
            notebook_id=None,
            require_source_refs=True,
            force=True,
        ),
        query_runner=fake_query,
    )

    assert result.ok == ["node-a", "node-b"]
    assert len(calls) == 2
    assert "node-a" in calls[0]
    assert "node-b" in calls[1]
    assert (out_dir / "node-a.yaml").exists()
    assert json.loads((out_dir / "_nlm_batch_state.json").read_text(encoding="utf-8"))[
        "completed"
    ] == [
        "node-a",
        "node-b",
    ]


def test_missing_nlm_binary_gives_actionable_error(monkeypatch, tmp_path):
    """A missing `nlm` CLI must produce install guidance, not a raw traceback."""
    import subprocess

    import pytest

    from akms_nodes_gen import nlm_batch

    def _no_binary(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "nlm")

    monkeypatch.setattr(subprocess, "run", _no_binary)
    options = nlm_batch.QueryOptions(
        notebook_id="nb", source_ids=[], timeout=5, output_format="markdown"
    )
    with pytest.raises(RuntimeError, match="nlm.*not found.*install"):
        nlm_batch.run_nlm_query("q", options)
