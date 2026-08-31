"""Tests for cli/commands.py — Phase 5: Developer CLI.

Coverage:
- promote: tentative → established (local nodes only)
- suppress: → draft
- deprecate: → deprecated
- status: graph_status report
- Error handling: node not found, wrong status
"""

from __future__ import annotations

import json

import frontmatter as fm
import pytest

from akms.cli.commands import build_parser, main

from .conftest import make_global_node, make_local_node


# ═══════════════════════════════════════════════════════════════════════
#  Promote
# ═══════════════════════════════════════════════════════════════════════


class TestPromote:
    def test_promotes_tentative_to_established(self, tmp_vault, tmp_repo):
        make_local_node(tmp_repo, id="tent-node", status="tentative")

        exit_code = main(["--repo", str(tmp_repo), "promote", "tent-node"])

        assert exit_code == 0
        node_path = tmp_repo / "knowledge" / "local-nodes" / "tent-node.md"
        post = fm.load(str(node_path))
        assert post.metadata["status"] == "established"

    def test_cannot_promote_non_tentative(self, tmp_vault, tmp_repo):
        make_local_node(tmp_repo, id="est-node", status="established")

        exit_code = main(["--repo", str(tmp_repo), "promote", "est-node"])
        assert exit_code == 1

    def test_node_not_found(self, tmp_vault, tmp_repo):
        exit_code = main(["--repo", str(tmp_repo), "promote", "nonexistent"])
        assert exit_code == 1


# ═══════════════════════════════════════════════════════════════════════
#  Suppress
# ═══════════════════════════════════════════════════════════════════════


class TestSuppress:
    def test_suppresses_to_draft(self, tmp_vault, tmp_repo):
        make_local_node(tmp_repo, id="node-x", status="tentative")

        exit_code = main(["--repo", str(tmp_repo), "suppress", "node-x"])

        assert exit_code == 0
        node_path = tmp_repo / "knowledge" / "local-nodes" / "node-x.md"
        post = fm.load(str(node_path))
        assert post.metadata["status"] == "draft"

    def test_suppress_node_not_found(self, tmp_vault, tmp_repo):
        exit_code = main(["--repo", str(tmp_repo), "suppress", "ghost"])
        assert exit_code == 1


# ═══════════════════════════════════════════════════════════════════════
#  Deprecate
# ═══════════════════════════════════════════════════════════════════════


class TestDeprecate:
    def test_deprecates_node(self, tmp_vault, tmp_repo):
        make_local_node(tmp_repo, id="old-node", status="established")

        exit_code = main(["--repo", str(tmp_repo), "deprecate", "old-node"])

        assert exit_code == 0
        node_path = tmp_repo / "knowledge" / "local-nodes" / "old-node.md"
        post = fm.load(str(node_path))
        assert post.metadata["status"] == "deprecated"


# ═══════════════════════════════════════════════════════════════════════
#  Status
# ═══════════════════════════════════════════════════════════════════════


class TestStatus:
    def test_status_runs(self, tmp_vault, tmp_repo, capsys, monkeypatch):
        from akms import telemetry

        telemetry._provider = None
        telemetry._tracer = None
        monkeypatch.delenv("AKMS_TELEMETRY", raising=False)
        make_global_node(tmp_vault, id="node-a", confidence=0.90)

        exit_code = main(["--repo", str(tmp_repo), "status"])

        assert exit_code == 0
        assert telemetry._provider is not None
        telemetry._provider.force_flush()
        captured = capsys.readouterr()
        assert "AKMS Graph Health Report" in captured.out
        assert "trace_id" not in captured.out
        assert "trace_id" not in captured.err


class TestQuery:
    def test_query_returns_ranked_nodes_as_json(self, tmp_vault, tmp_repo, capsys):
        make_global_node(
            tmp_vault,
            id="plasticity-node",
            title="Plasticity Node",
            tags=["plasticity"],
        )

        exit_code = main(["query", "plasticity", "--repo", str(tmp_repo)])

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["count"] == 1
        assert payload["nodes"][0]["id"] == "plasticity-node"
        assert payload["graph_path"].endswith("knowledge/graph/graph.json")

    def test_query_serialization_normalizes_nullable_fields_and_string_tags(
        self,
        monkeypatch,
        tmp_repo,
        capsys,
    ):
        from akms.cli import commands

        monkeypatch.setattr(commands, "_load_cli_config", lambda _repo: object())
        monkeypatch.setattr(
            commands,
            "_load_cli_graph",
            lambda *_args: (object(), tmp_repo / "graph.json"),
        )
        monkeypatch.setattr(
            "akms.graph.query_subgraph.query_subgraph",
            lambda *_args, **_kwargs: [
                (
                    "node-a",
                    {
                        "confidence": None,
                        "domain": None,
                        "node_origin": None,
                        "tags": "plasticity",
                        "title": None,
                    },
                )
            ],
        )

        exit_code = main(["query", "plasticity", "--repo", str(tmp_repo)])

        assert exit_code == 0
        assert json.loads(capsys.readouterr().out)["nodes"] == [
            {
                "confidence": 0.0,
                "domain": "",
                "id": "node-a",
                "node_origin": "",
                "tags": ["plasticity"],
                "title": "",
            }
        ]

    def test_query_missing_explicit_graph_is_error(self, tmp_repo, capsys):
        exit_code = main(
            [
                "query",
                "plasticity",
                "--repo",
                str(tmp_repo),
                "--graph",
                "missing.json",
            ]
        )

        assert exit_code == 1
        assert "Graph file not found" in capsys.readouterr().err


class TestLoadout:
    def test_loadout_writes_canonical_file(self, tmp_vault, tmp_repo, capsys):
        make_global_node(
            tmp_vault,
            id="solver-node",
            title="Solver Node",
            tags=["solver"],
        )

        exit_code = main(
            [
                "loadout",
                "task-7",
                "--phase",
                "2",
                "--tags",
                "solver",
                "--repo",
                str(tmp_repo),
            ]
        )

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        expected = tmp_repo / "knowledge" / "loadouts" / "2-task-7-loadout.md"
        assert payload["loadout_path"] == str(expected)
        assert payload["node_count"] == 1
        assert expected.exists()
        assert "graph_version:" in expected.read_text()

    def test_loadout_rejects_path_like_task_id(self, tmp_repo, capsys):
        exit_code = main(
            [
                "loadout",
                "../escape",
                "--phase",
                "2",
                "--tags",
                "solver",
                "--repo",
                str(tmp_repo),
            ]
        )

        assert exit_code == 1
        assert "task_id must be" in capsys.readouterr().err


# ═══════════════════════════════════════════════════════════════════════
#  Parser
# ═══════════════════════════════════════════════════════════════════════


class TestParser:
    def test_no_command_shows_help(self, tmp_vault, tmp_repo, capsys):
        exit_code = main([])
        assert exit_code == 0

    def test_parser_has_all_commands(self):
        parser = build_parser()
        # Verify subcommands exist by trying to parse them
        args = parser.parse_args(["promote", "some-id"])
        assert args.command == "promote"
        assert args.node_id == "some-id"

        query_args = parser.parse_args(["query", "tag-a", "tag-b"])
        assert query_args.command == "query"
        assert query_args.tags == ["tag-a", "tag-b"]

        loadout_args = parser.parse_args(
            [
                "loadout",
                "task-1",
                "--phase",
                "1",
                "--tags",
                "tag-a",
            ]
        )
        assert loadout_args.command == "loadout"
        assert loadout_args.task_id == "task-1"

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["--repo", "before", "status"], "before"),
            (["status", "--repo", "after"], "after"),
        ],
    )
    def test_repo_flag_accepted_before_or_after_subcommand(self, argv, expected):
        assert build_parser().parse_args(argv).repo == expected


def test_import_agent_class_supports_codex_path():
    from akms.agents.base_codex import AKMSCodexAgent
    from akms.cli.commands import _import_agent_class

    cls = _import_agent_class("akms.agents.base_codex.AKMSCodexAgent")
    assert cls is AKMSCodexAgent


def test_import_agent_class_rejects_non_subclass(monkeypatch):
    from akms.cli.commands import _import_agent_class

    class NotAgent:
        pass

    monkeypatch.setattr(
        "akms.cli.commands.importlib.import_module",
        lambda _: type("M", (), {"NotAgent": NotAgent})(),
    )

    with pytest.raises(TypeError, match="not a subclass of AKMSAgent"):
        _import_agent_class("fake.module.NotAgent")
