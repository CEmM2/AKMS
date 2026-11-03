"""The ``builtin`` mirror provider: the exporter shipped in akms, run as a subprocess."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from akms.graph.build_graph import build_graph
from akms.graph.generate_mirror import generate_mirror
from akms.graph.mirror_provider import (
    MirrorProviderError,
    get_provider,
    list_providers,
    refresh_mirror,
)
from akms.graph.providers.repo2md import (
    BuiltinMirrorProvider,
    Repo2mdMirrorProvider,
    build_repo2md_argv,
    validate_repo2md_export,
)
from akms.schema.models import MirrorConfig

GENERATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)

_SOURCE = (
    '"""A value."""\n\n\ndef value() -> int:\n    """Return one."""\n    return 1\n'
)


def _repo(tmp_path: Path, *, layout: str | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "value.py").write_text(_SOURCE, encoding="utf-8")
    if layout is not None:
        (repo / layout).mkdir()
    return repo


def _config(**kwargs) -> MirrorConfig:
    return MirrorConfig(
        provider="builtin",
        selection_mode="full",
        generated_at_source="request",
        **kwargs,
    )


def _mirror_ids(repo: Path, tmp_path: Path) -> list[str]:
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    graph = build_graph(repo, global_vault=vault)
    return sorted(
        node
        for node, attrs in graph.nodes(data=True)
        if attrs.get("node_origin") == "code-mirror"
    )


class TestRegistration:
    def test_builtin_is_registered(self):
        assert "builtin" in list_providers()
        assert isinstance(get_provider("builtin"), BuiltinMirrorProvider)

    def test_runs_the_packaged_exporter_and_ignores_config_command(
        self, tmp_path: Path
    ):
        provider = BuiltinMirrorProvider()
        config = _config(command=["some-other-repo-wiki"])

        assert provider.command(config) == [sys.executable, "-m", "akms.repo_wiki"]

    def test_requests_the_repositorys_knowledge_dir(self, tmp_path: Path):
        provider = BuiltinMirrorProvider()
        assert provider.knowledge_dir(_repo(tmp_path)) == ".knowledge"
        legacy = _repo(tmp_path / "legacy", layout="knowledge")
        assert provider.knowledge_dir(legacy) == "knowledge"

    def test_external_provider_never_passes_knowledge_dir(self, tmp_path: Path):
        argv = build_repo2md_argv(
            config=MirrorConfig(provider="repo2md"),
            repo_root=tmp_path,
            output_root=tmp_path,
            phase=1,
            generated_at=GENERATED_AT,
            selection_mode="full",
        )
        assert "--knowledge-dir" not in argv

    def test_external_provider_never_passes_strict_parse(self, tmp_path: Path):
        config = MirrorConfig(provider="repo2md", strict_parse=True)
        argv = build_repo2md_argv(
            config=config,
            repo_root=tmp_path,
            output_root=tmp_path,
            phase=1,
            generated_at=GENERATED_AT,
            selection_mode="full",
        )
        assert "--strict-parse" not in argv
        assert Repo2mdMirrorProvider().strict_parse(config) is False

    def test_builtin_passes_strict_parse_only_when_configured(self, tmp_path: Path):
        provider = BuiltinMirrorProvider()
        assert provider.strict_parse(_config()) is False
        assert provider.strict_parse(_config(strict_parse=True)) is True

        def argv_for(config: MirrorConfig) -> list[str]:
            return build_repo2md_argv(
                config=config,
                command=provider.command(config),
                strict_parse=provider.strict_parse(config),
                provider="builtin",
                repo_root=tmp_path,
                output_root=tmp_path,
                phase=1,
                generated_at=GENERATED_AT,
                selection_mode="full",
            )

        assert "--strict-parse" not in argv_for(_config())
        assert "--strict-parse" in argv_for(_config(strict_parse=True))


@pytest.mark.integration
class TestExport:
    def test_new_repository_mirror_lands_in_dot_knowledge_and_loads(
        self, tmp_path: Path
    ):
        repo = _repo(tmp_path)

        result = refresh_mirror(repo, 1, config=_config())

        assert result["provider"] == "builtin"
        assert result["success"] is True
        assert [m["generated_path"] for m in result["mirrors"]] == [
            ".knowledge/code-mirror/pkg/value.md"
        ]
        assert result["provider_metadata"]["cli"] == (
            "python -m akms.repo_wiki export-akms"
        )
        assert not (repo / "knowledge").exists()
        assert _mirror_ids(repo, tmp_path) == ["mirror-pkg-value"]

    def test_legacy_knowledge_repository_keeps_its_directory(self, tmp_path: Path):
        repo = _repo(tmp_path, layout="knowledge")

        result = refresh_mirror(repo, 1, config=_config())

        assert [m["generated_path"] for m in result["mirrors"]] == [
            "knowledge/code-mirror/pkg/value.md"
        ]
        assert not (repo / ".knowledge").exists()
        assert _mirror_ids(repo, tmp_path) == ["mirror-pkg-value"]

    def test_prune_removes_stale_mirrors_under_dot_knowledge(self, tmp_path: Path):
        repo = _repo(tmp_path)
        (repo / "pkg" / "old.py").write_text("OLD = 1\n", encoding="utf-8")
        refresh_mirror(repo, 1, config=_config())
        stale = repo / ".knowledge" / "code-mirror" / "pkg" / "old.md"
        assert stale.is_file()

        (repo / "pkg" / "old.py").unlink()
        refresh_mirror(repo, 1, config=_config(prune=True))

        assert not stale.exists()
        assert _mirror_ids(repo, tmp_path) == ["mirror-pkg-value"]

    def test_exporter_failure_is_reported_as_builtin(self, tmp_path: Path):
        repo = _repo(tmp_path)

        with pytest.raises(MirrorProviderError) as error:
            refresh_mirror(
                repo,
                1,
                config=MirrorConfig(
                    provider="builtin",
                    selection_mode="paths",
                    generated_at_source="request",
                ),
                source_files=["pkg/missing.py"],
            )

        assert error.value.provider == "builtin"


def _repo_with_unparsable_source(tmp_path: Path) -> Path:
    repo = _repo(tmp_path)
    (repo / "pkg" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    return repo


@pytest.mark.integration
class TestUnparsableSources:
    def test_default_refresh_skips_the_unparsable_source(self, tmp_path: Path):
        repo = _repo_with_unparsable_source(tmp_path)

        result = refresh_mirror(repo, 1, config=_config(), drift_check=True)

        assert result["success"] is True
        assert [m["generated_path"] for m in result["mirrors"]] == [
            ".knowledge/code-mirror/pkg/value.md"
        ]
        assert result["provider_metadata"]["parse_skipped"] == ["pkg/broken.py"]
        assert result["provider_metadata"]["skipped_count"] == 1
        assert _mirror_ids(repo, tmp_path) == ["mirror-pkg-value"]

    def test_explicit_selection_drift_ignores_the_unparsable_source(
        self, tmp_path: Path
    ):
        repo = _repo_with_unparsable_source(tmp_path)

        result = refresh_mirror(
            repo,
            1,
            config=_config(),
            source_files=["pkg/value.py", "pkg/broken.py"],
            drift_check=True,
        )

        assert result["success"] is True
        assert result["provider_metadata"]["parse_skipped"] == ["pkg/broken.py"]

    def test_clean_refresh_reports_no_parse_skipped(self, tmp_path: Path):
        result = refresh_mirror(_repo(tmp_path), 1, config=_config())

        assert result["provider_metadata"]["parse_skipped"] == []

    def test_strict_parse_makes_the_unparsable_source_a_failure(self, tmp_path: Path):
        repo = _repo_with_unparsable_source(tmp_path)

        with pytest.raises(MirrorProviderError) as error:
            refresh_mirror(repo, 1, config=_config(strict_parse=True))

        assert error.value.provider == "builtin"
        assert "pkg/broken.py" in str(error.value)
        assert not (repo / ".knowledge" / "code-mirror").exists()

    def test_generate_mirror_cli_warns_on_stderr(self, tmp_path: Path, capsys):
        from akms.cli.commands import main

        repo = _repo_with_unparsable_source(tmp_path)

        assert (
            main(
                [
                    "generate-mirror",
                    "--repo",
                    str(repo),
                    "--path",
                    "pkg/value.py",
                    "--path",
                    "pkg/broken.py",
                    "--json",
                ]
            )
            == 0
        )

        captured = capsys.readouterr()
        assert "warning: skipped 1 unparsable source(s)" in captured.err
        assert "pkg/broken.py" in captured.err
        assert '"parse_skipped"' in captured.out


class TestValidation:
    def test_rejects_mirrors_outside_the_requested_knowledge_dir(self, tmp_path: Path):
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "content_ref": "code-mirror/pkg/value.md",
                    "generated_path": "knowledge/code-mirror/pkg/value.md",
                    "node_id": "mirror-pkg-value",
                    "source_path": "pkg/value.py",
                }
            ],
        }

        with pytest.raises(MirrorProviderError) as error:
            validate_repo2md_export(
                export,
                repo_root=tmp_path,
                output_root=tmp_path,
                config=MirrorConfig(),
                knowledge_dir=".knowledge",
                provider="builtin",
            )

        assert error.value.code == "path_escape"
        assert error.value.provider == "builtin"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.mark.integration
class TestDefault:
    def test_builtin_is_the_default_provider(self, tmp_path: Path):
        repo = _repo(tmp_path)

        result = generate_mirror(repo, 1, source_files=["pkg/value.py"])

        assert result["provider"] == "builtin"
        assert [m["generated_path"] for m in result["mirrors"]] == [
            ".knowledge/code-mirror/pkg/value.md"
        ]

    def test_changed_selection_without_a_git_repo_selects_nothing(self, tmp_path: Path):
        repo = _repo(tmp_path)

        result = generate_mirror(repo, 1)

        assert result["provider"] == "builtin"
        assert result["success"] is True
        assert result["mirrors"] == []
        assert result["provider_metadata"]["selection"] == "skipped"
        assert not (repo / ".knowledge").exists()

    def test_changed_selection_without_the_base_branch_selects_nothing(
        self, tmp_path: Path
    ):
        repo = _repo(tmp_path)
        _git(repo, "init", "-q", "-b", "trunk")

        result = generate_mirror(repo, 1, parent_branch="main")

        assert result["mirrors"] == []
        assert "'main'" in result["provider_metadata"]["reason"]

    def test_changed_selection_exports_files_changed_since_the_base(
        self, tmp_path: Path
    ):
        repo = _repo(tmp_path)
        _git(repo, "init", "-q", "-b", "main")
        _git(
            repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "."
        )
        _git(
            repo,
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "base",
        )
        (repo / "pkg" / "other.py").write_text("OTHER = 1\n", encoding="utf-8")
        _git(repo, "add", "pkg/other.py")
        (repo / "pkg" / "value.py").write_text(
            _SOURCE + "\nEXTRA = 2\n", encoding="utf-8"
        )

        result = generate_mirror(repo, 1, parent_branch="main")

        assert sorted(m["source_file"] for m in result["mirrors"]) == [
            "pkg/other.py",
            "pkg/value.py",
        ]


@pytest.mark.integration
class TestSkippedSelection:
    def test_require_success_turns_a_skipped_selection_into_a_failure(
        self, tmp_path: Path
    ):
        repo = _repo(tmp_path)

        with pytest.raises(MirrorProviderError) as error:
            refresh_mirror(
                repo,
                1,
                config=MirrorConfig(provider="builtin", require_success=True),
            )

        assert error.value.code == "selection_unavailable"
        assert error.value.provider == "builtin"

    def test_generate_mirror_cli_warns_on_stderr(self, tmp_path: Path, capsys):
        from akms.cli.commands import main

        repo = _repo(tmp_path)

        assert main(["generate-mirror", "--repo", str(repo), "--json"]) == 0

        captured = capsys.readouterr()
        assert captured.err.startswith("warning: no files selected: ")
        assert '"selection": "skipped"' in captured.out
