"""Tests for the built-in converter + validator post-processors and their wiring
as defaults in ``BatchRunConfig``."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from akms_nodes_gen import nlm_batch
from akms_nodes_gen.tools import CONVERTER_PATH, VALIDATOR_PATH
from akms_nodes_gen.tools import validate_markdown, yaml_to_markdown


def _sample_node_yaml() -> dict:
    return {
        "id": "test-node-a",
        "title": "Test Node A",
        "domain": "computational-mechanics",
        "subdomain": "plasticity",
        "tags": ["return-mapping", "plasticity", "newton"],
        "status": "tentative",
        "confidence": 0.9,
        "source": "hybrid",
        "edges": [
            {
                "to": "skill-computational-mechanics",
                "type": "requires",
                "weight": 1.0,
                "note": "needs CM background",
            }
        ],
        "context_size": "medium",
        "reading_priority": "full",
        "content_ref": None,
        "akms_schema": "v2",
        "summary": (
            "This node describes the radial return mapping algorithm for J2 plasticity. "
            "It uses an elastic predictor and plastic corrector split enforced by a scalar "
            "Newton iteration on the plastic multiplier. Source [Simo & Hughes 1998]."
        ),
        "core_concept": "Operator split into trial elastic state then plastic correction.",
        "math_formulation": {
            "equations": [
                {
                    "label": "yield function",
                    "latex": r"f = \|s\| - \sqrt{2/3}\,\sigma_y",
                    "source_ref": "Simo & Hughes 1998 Eq. 3.1",
                }
            ]
        },
        "algorithms": [
            {
                "label": "radial return",
                "source_ref": "Simo & Hughes 1998 Box 3.2",
                "steps": [
                    {"cmd": "Compute trial stress", "math": r"s^{tr} = 2\mu e"},
                    {"cmd": "Check yield", "math": "f^{tr} > 0"},
                ],
            }
        ],
        "pitfalls": [
            {
                "name": "inconsistent tangent",
                "description": "Using elastic tangent destroys quadratic convergence.",
                "source_ref": "Simo & Hughes 1998 p. 124",
            }
        ],
        "references": ["Simo & Hughes 1998"],
    }


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


# ── (a) converter turns YAML into a schema-valid .md ──────────────────────────


def test_converter_produces_schema_valid_markdown(tmp_path: Path) -> None:
    yaml_path = tmp_path / "test-node-a.yaml"
    _write_yaml(yaml_path, _sample_node_yaml())

    md_path = yaml_to_markdown.convert_file(yaml_path)

    assert md_path == yaml_path.with_suffix(".md")
    text = md_path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "## Summary" in text
    assert "# Test Node A" in text
    assert "akms_schema: v2" in text

    # The produced markdown must pass the canonical validator with no errors.
    code, lines = validate_markdown.validate_file(md_path)
    assert code == 0, f"validator reported issues: {lines}"


def test_converter_frontmatter_preserves_schema_fields(tmp_path: Path) -> None:
    yaml_path = tmp_path / "node.yaml"
    _write_yaml(yaml_path, _sample_node_yaml())
    md_path = yaml_to_markdown.convert_file(yaml_path)

    import frontmatter as fm_lib

    post = fm_lib.load(str(md_path))
    fm = dict(post.metadata)
    assert fm["id"] == "test-node-a"
    assert fm["title"] == "Test Node A"
    assert fm["status"] == "tentative"
    assert fm["tags"] == ["return-mapping", "plasticity", "newton"]
    assert fm["edges"][0]["to"] == "skill-computational-mechanics"
    # Body-only keys must NOT leak into the frontmatter.
    assert "summary" not in fm
    assert "algorithms" not in fm


def test_converter_missing_id_fails(tmp_path: Path) -> None:
    yaml_path = tmp_path / "bad.yaml"
    bad = _sample_node_yaml()
    del bad["id"]
    _write_yaml(yaml_path, bad)

    with pytest.raises(ValueError, match="id"):
        yaml_to_markdown.convert_file(yaml_path)


def test_converter_renders_structured_algorithm_commands() -> None:
    node = _sample_node_yaml()
    node["algorithms"] = [
        {
            "label": "structured loop",
            "steps": [
                {"cmd": "State", "math": r"s \gets 0"},
                {"cmd": "For", "math": r"i \gets 1,\ldots,n"},
                {"cmd": "If", "math": r"a_i > 0"},
                {"cmd": "State", "math": r"s \gets s + a_i"},
                {"cmd": "Else", "math": ""},
                {"cmd": "State", "math": r"s \gets s - a_i"},
                {"cmd": "EndIf", "math": ""},
                {"cmd": "EndFor", "math": ""},
                {"cmd": "Return", "math": "s"},
            ],
            "source_ref": "Attached source, Algorithm 1",
        }
    ]

    text = yaml_to_markdown.build_markdown(node)

    assert r"\State $s \gets 0$" in text
    assert r"\For{$i \gets 1,\ldots,n$}" in text
    assert r"\If{$a_i > 0$}" in text
    assert r"\Else" in text
    assert r"\EndIf" in text
    assert r"\EndFor" in text
    assert r"\Return $s$" in text
    assert r"\State For" not in text


def test_converter_cli_exit_codes(tmp_path: Path) -> None:
    good = tmp_path / "good.yaml"
    _write_yaml(good, _sample_node_yaml())
    assert yaml_to_markdown.main([str(good), "-v"]) == 0

    bad = tmp_path / "bad.yaml"
    bad.write_text("not: [a, valid, node\n", encoding="utf-8")  # malformed YAML
    assert yaml_to_markdown.main([str(bad)]) != 0


# ── (b) validator passes on good .md, fails on bad .md ────────────────────────


def test_validator_passes_on_good_md(tmp_path: Path) -> None:
    yaml_path = tmp_path / "node.yaml"
    _write_yaml(yaml_path, _sample_node_yaml())
    md_path = yaml_to_markdown.convert_file(yaml_path)

    assert validate_markdown.main([str(md_path), "--validate-only", "-v"]) == 0


def test_validator_fails_on_bad_md(tmp_path: Path) -> None:
    bad_md = tmp_path / "bad.md"
    # Missing required schema fields (no domain/tags/confidence/...), wrong schema.
    bad_md.write_text(
        "---\nid: bad-node\ntitle: Bad\nakms_schema: v1\n---\n\n# Bad\n\nNo summary here.\n",
        encoding="utf-8",
    )
    code, lines = validate_markdown.validate_file(bad_md)
    assert code == 1
    assert lines  # issues reported
    assert validate_markdown.main([str(bad_md), "--validate-only"]) == 1


def test_validator_missing_file(tmp_path: Path) -> None:
    code, lines = validate_markdown.validate_file(tmp_path / "nope.md")
    assert code != 0
    assert any("not found" in line for line in lines)


# ── (c) BatchRunConfig defaults converter/validator to the built-ins ──────────


def _minimal_config(**overrides) -> nlm_batch.BatchRunConfig:
    base = dict(
        plan_path=Path("plan.json"),
        out_dir=Path("out"),
        prompt_file=Path("prompt.md"),
        output_format="yaml",
        timeout=1.0,
    )
    base.update(overrides)
    return nlm_batch.BatchRunConfig(**base)


def test_config_defaults_to_builtin_postprocessors() -> None:
    cfg = _minimal_config()
    assert cfg.converter == CONVERTER_PATH
    assert cfg.validator == VALIDATOR_PATH
    assert cfg.converter.exists()
    assert cfg.validator.exists()


# ── (d) overrides and opt-out still work ──────────────────────────────────────


def test_config_override_converter_and_validator() -> None:
    custom_c = Path("/custom/converter.py")
    custom_v = Path("/custom/validator.py")
    cfg = _minimal_config(converter=custom_c, validator=custom_v)
    assert cfg.converter == custom_c
    assert cfg.validator == custom_v


def test_config_opt_out_with_none() -> None:
    cfg = _minimal_config(converter=None, validator=None)
    assert cfg.converter is None
    assert cfg.validator is None


def test_config_partial_override_keeps_other_default() -> None:
    cfg = _minimal_config(converter=Path("/custom/converter.py"))
    assert cfg.converter == Path("/custom/converter.py")
    assert cfg.validator == VALIDATOR_PATH


# ── end-to-end: run_batch uses the built-ins to emit a valid .md ──────────────


def _write_plan(path: Path) -> None:
    import json

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
                                "id": "test-node-a",
                                "title": "Test Node A",
                                "status": "new",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_run_batch_default_postprocessors_emit_valid_markdown(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Generate {output_format}.", encoding="utf-8")
    out_dir = tmp_path / "out"

    node = _sample_node_yaml()
    # Edge must target a known id; skill-computational-mechanics is a TIER1 id.

    def fake_query(question: str, options: nlm_batch.QueryOptions) -> str:
        return "```yaml\n" + yaml.safe_dump(node, sort_keys=False) + "```"

    result = nlm_batch.run_batch(
        nlm_batch.BatchRunConfig(
            plan_path=plan_path,
            out_dir=out_dir,
            prompt_file=prompt_path,
            output_format="yaml",
            timeout=5.0,
            batch_id="B1",
            force=True,
        ),
        query_runner=fake_query,
    )

    assert result.ok == ["test-node-a"], result.failed
    md_path = out_dir / "test-node-a.md"
    assert md_path.exists()
    code, lines = validate_markdown.validate_file(md_path)
    assert code == 0, lines
