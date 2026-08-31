"""Hermetic pin: F3 may import only documented public AKMS surfaces.

Loads ``Packages/AKMS/release/failure_memory_public_api_pin.json`` and asserts
each listed public symbol is importable. Also asserts a small set of forbidden
private paths are not advertised as public and that repo2md is not imported.
"""

from __future__ import annotations

import importlib
import hashlib
import json
import sys
from pathlib import Path

import pytest

_PIN_PATH = (
    Path(__file__).resolve().parents[2]
    / "release"
    / "failure_memory_public_api_pin.json"
)
_PACKAGE_ROOT = _PIN_PATH.parent.parent

_EXPECTED_ALLOWED_PYTHON = {
    "akms.task_context.resolve_task_service": (
        "resolve_task",
        "load_task_mapping",
        "ResolveTaskResult",
    ),
    "akms.task_context.review": ("resolve_reviewer_context",),
    "akms.task_context.models": (
        "TASK_ROUTE_INDEX_SCHEMA_VERSION",
        "normalize_repository_path",
        "RouteRecord",
        "RouteValidationIssue",
        "RouteIndexValidationError",
        "TaskRouteIndex",
    ),
    "akms.task_context.routes": ("parse_route_index", "validate_route_index_nodes"),
    "akms.task_context.resolve": (
        "TaskSeeds",
        "ResolvedSeeds",
        "TaskPathSpec",
        "canonicalize_task_path_specs",
        "resolve_task_seeds",
    ),
    "akms.task_context.query": (
        "query_task_knowledge",
        "TaskKnowledgeQueryResult",
        "NodeSelection",
        "SelectionClass",
        "RequiredNodeUnavailableError",
    ),
    "akms.task_context.manifest": (
        "create_resolution_manifest",
        "write_resolution_manifest",
        "load_resolution_manifest",
        "validate_resolution_manifest",
        "resolution_manifest_is_stale",
        "ResolutionManifest",
    ),
    "akms.graph.generate_loadout": ("generate_loadout", "select_loadout_mode"),
    "akms.graph.generate_mirror": ("generate_mirror", "generate_mirror_legacy"),
    "akms.graph.mirror_provider": (
        "MirrorRequest",
        "MirrorResult",
        "MirrorProvider",
        "MirrorProviderError",
        "UnknownMirrorProviderError",
        "register_provider",
        "list_providers",
        "get_provider",
        "run_mirror_provider",
        "refresh_mirror",
        "resolve_mirror_config",
        "public_provider_identity",
    ),
    "akms.graph.build_graph": ("build_graph", "load_graph"),
    "akms.graph.query_subgraph": ("query_subgraph",),
    "akms.schema.models": (
        "PropagationConfig",
        "MirrorConfig",
        "CodeMirrorNodeFrontmatter",
        "AgentRole",
        "LoadoutMode",
    ),
    "akms": ("AKMS_SCHEMA_VERSION", "__version__"),
}
_PUBLIC_CLI_MCP_SOURCES = {
    "Packages/AKMS/src/akms/cli/commands.py",
    "Packages/AKMS/src/akms/cli/provider_commands.py",
    "Packages/AKMS/src/akms/orchestrator/mcp_tools.py",
}


def _public_source_path(module_name: str) -> Path:
    package_path = _PACKAGE_ROOT / "src" / Path(*module_name.split("."))
    return (
        package_path / "__init__.py"
        if module_name == "akms"
        else package_path.with_suffix(".py")
    )


def _public_source_digest(source_paths: list[str]) -> str:
    digest = hashlib.sha256()
    workspace = _PACKAGE_ROOT.parents[1]
    for relative in source_paths:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((workspace / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@pytest.fixture(scope="module")
def pin() -> dict:
    # The release pin is generated from the private workspace and is
    # deliberately not exported to the public repo (it digests private
    # sources). Skip rather than error where it is absent; the pin is
    # regenerated and enforced at release time in the private repo.
    if not _PIN_PATH.is_file():
        pytest.skip(f"public API pin not shipped in this tree: {_PIN_PATH}")
    data = json.loads(_PIN_PATH.read_text(encoding="utf-8"))
    assert data.get("pin_kind") == "akms_failure_memory_public_api"
    assert data.get("akms_schema_version") == "v2"
    return data


class TestPublicApiPin:
    def test_pin_lists_core_surfaces(self, pin: dict):
        modules = {entry["module"] for entry in pin["allowed_python"]}
        assert "akms.task_context.resolve_task_service" in modules
        assert "akms.task_context.review" in modules
        assert "akms.graph.generate_loadout" in modules
        assert "akms.graph.generate_mirror" in modules
        assert "akms.graph.mirror_provider" in modules
        assert "akms resolve-task" in pin["allowed_cli"]
        assert "repo2md_provider" in pin["related_pins"]

    def test_allowed_python_surface_is_exact_and_has_no_wildcards(self, pin: dict):
        actual = {
            entry["module"]: tuple(entry.get("symbols") or [])
            for entry in pin["allowed_python"]
        }
        assert actual == _EXPECTED_ALLOWED_PYTHON
        assert all("*" not in symbols for symbols in actual.values())

    def test_pin_has_reproducible_non_circular_akms_identity(self, pin: dict):
        identity = pin["akms_identity"]
        assert identity["kind"] == "public_source_sha256"
        assert identity["algorithm"] == "sha256"
        expected_paths = sorted(
            {
                *(
                    str(
                        _public_source_path(module).relative_to(
                            _PACKAGE_ROOT.parents[1]
                        )
                    )
                    for module in _EXPECTED_ALLOWED_PYTHON
                ),
                *_PUBLIC_CLI_MCP_SOURCES,
            }
        )
        assert identity["source_paths"] == expected_paths
        assert identity["sha256"] == _public_source_digest(expected_paths)

    def test_import_each_allowed_symbol(self, pin: dict):
        for entry in pin["allowed_python"]:
            module_name = entry["module"]
            symbols = entry.get("symbols") or []
            mod = importlib.import_module(module_name)
            for name in symbols:
                assert hasattr(mod, name), (
                    f"public pin symbol missing: {module_name}.{name}"
                )
                assert getattr(mod, name) is not None

    def test_every_listed_cli_and_mcp_surface_is_registered(
        self, pin: dict, tmp_repo, tmp_vault
    ):
        from akms.cli.commands import build_parser
        from akms.orchestrator.mcp_tools import create_mcp_server
        from mcp.types import ListToolsRequest

        parser = build_parser()
        actions = [a for a in parser._subparsers._group_actions if a.dest == "command"]
        cli_commands = set(actions[0].choices)
        assert {
            entry.removeprefix("akms ") for entry in pin["allowed_cli"]
        } <= cli_commands

        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        handler = server.request_handlers[ListToolsRequest]
        raw = __import__("asyncio").run(handler(ListToolsRequest(method="tools/list")))
        result = raw.root if hasattr(raw, "root") else raw
        assert set(pin["allowed_mcp_tools"]) <= {tool.name for tool in result.tools}

    def test_named_entrypoints_callable(self):
        from akms.graph.generate_loadout import generate_loadout
        from akms.graph.generate_mirror import generate_mirror
        from akms.graph.mirror_provider import list_providers, run_mirror_provider
        from akms.task_context.resolve_task_service import resolve_task
        from akms.task_context.review import resolve_reviewer_context

        assert callable(resolve_task)
        assert callable(resolve_reviewer_context)
        assert callable(generate_loadout)
        assert callable(generate_mirror)
        assert callable(run_mirror_provider)
        assert "legacy" in list_providers()

    def test_forbidden_private_paths_documented(self, pin: dict):
        forbidden_blob = "\n".join(pin.get("forbidden") or []).lower()
        for needle in (
            "import repo2md",
            "orchestrator",
            "frozen",
            "shell",
        ):
            assert needle in forbidden_blob

    def test_no_repo2md_python_import_from_public_surfaces(self):
        """Importing public surfaces must not pull in repo2md as a package."""
        # Clear any accidental prior import from other tests.
        doomed = [n for n in sys.modules if n == "repo2md" or n.startswith("repo2md.")]
        for n in doomed:
            del sys.modules[n]

        import akms.graph.generate_mirror  # noqa: F401
        import akms.graph.mirror_provider  # noqa: F401
        import akms.graph.providers.repo2md  # provider module is OK; package is not
        import akms.task_context.resolve_task_service  # noqa: F401

        assert "repo2md" not in sys.modules
        assert not any(n.startswith("repo2md.") for n in sys.modules)

        # Provider source must not import the external package.
        src = Path(akms.graph.providers.repo2md.__file__).read_text(encoding="utf-8")
        assert "import repo2md" not in src
        assert "from repo2md" not in src

    def test_related_repo2md_pin_exists(self, pin: dict):
        rel = pin["related_pins"]["repo2md_provider"]
        # Path is repo-relative from AKMS workspace root (Packages/AKMS/...).
        workspace = Path(__file__).resolve().parents[4]
        path = workspace / rel
        if not path.is_file():
            # Fallback: relative to Packages/AKMS
            path = (
                Path(__file__).resolve().parents[2]
                / "release"
                / "repo2md_provider_pin.json"
            )
        assert path.is_file(), path
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("repo2md", {}).get("export_schema_version") == 1
        assert data.get("repo2md", {}).get("akms_schema_version") == "v2"
