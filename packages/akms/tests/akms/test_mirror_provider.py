"""Tests for the mirror-provider protocol (A2-4).

Coverage:
- Legacy default path is unchanged for existing generate_mirror callers
- Provider registry resolve / unknown provider
- MirrorConfig parse defaults and validation
- Fallback policy: explicit only, never silent
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from akms.graph.generate_mirror import generate_mirror, generate_mirror_legacy
from akms.graph.mirror_provider import (
    MirrorProviderError,
    MirrorRequest,
    MirrorResult,
    UnknownMirrorProviderError,
    get_provider,
    list_providers,
    public_provider_identity,
    refresh_mirror,
    register_provider,
    resolve_mirror_config,
    run_mirror_provider,
    unregister_provider,
)
from akms.schema.models import MirrorConfig, PropagationConfig
from akms.schema.validators import parse_propagation_config


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _write_py(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    (repo / "knowledge" / "code-mirror").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "knowledge" / "code-mirror").mkdir(parents=True)
    (tmp_path / "knowledge" / "graph").mkdir(parents=True)
    _write_py(
        tmp_path,
        "src/mod.py",
        '''\
        def greet(name: str) -> str:
            """Greet *name*."""
            return f"hi {name}"
        ''',
    )
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════════════════


class TestMirrorConfig:
    def test_defaults_are_legacy(self):
        cfg = MirrorConfig()
        assert cfg.provider == "legacy"
        assert cfg.fallback_on_error is False
        assert cfg.require_success is False
        assert cfg.command == ["repo-wiki"]
        assert cfg.expected_export_schema_version == 1
        assert cfg.expected_akms_schema_version == "v2"

    def test_propagation_config_includes_mirror(self):
        pc = PropagationConfig()
        assert isinstance(pc.mirror, MirrorConfig)
        assert pc.mirror.provider == "legacy"

    def test_parse_propagation_without_mirror_block(self, tmp_path: Path):
        path = tmp_path / "propagation_config.yaml"
        path.write_text(
            yaml.safe_dump(
                {"akms_schema": "v2", "global_vault": str(tmp_path / "vault")}
            ),
            encoding="utf-8",
        )
        pc = parse_propagation_config(path)
        assert pc.mirror.provider == "legacy"

    def test_parse_propagation_with_repo2md_block(self, tmp_path: Path):
        path = tmp_path / "propagation_config.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "akms_schema": "v2",
                    "mirror": {
                        "provider": "repo2md",
                        "command": ["repo-wiki"],
                        "timeout_seconds": 30,
                        "fallback_on_error": False,
                        "require_success": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        pc = parse_propagation_config(path)
        assert pc.mirror.provider == "repo2md"
        assert pc.mirror.timeout_seconds == 30
        assert pc.mirror.require_success is True

    def test_resolve_mirror_config_from_propagation(self):
        pc = PropagationConfig(mirror=MirrorConfig(provider="repo2md"))
        assert resolve_mirror_config(pc).provider == "repo2md"

    def test_resolve_mirror_config_passthrough(self):
        mc = MirrorConfig(provider="legacy", timeout_seconds=5)
        assert resolve_mirror_config(mc).timeout_seconds == 5

    def test_public_identity_has_no_secrets(self):
        cfg = MirrorConfig(
            provider="repo2md",
            command=["/secret/path/to/repo-wiki"],
        )
        ident = public_provider_identity(cfg)
        assert ident["provider"] == "repo2md"
        assert ident["command_basename"] == "repo-wiki"
        assert "/secret" not in str(ident)


# ═══════════════════════════════════════════════════════════════════════
#  Registry
# ═══════════════════════════════════════════════════════════════════════


class TestProviderRegistry:
    def test_builtin_providers_registered(self):
        names = list_providers()
        assert "legacy" in names
        assert "repo2md" in names

    def test_get_legacy_provider(self):
        p = get_provider("legacy")
        assert p.name == "legacy"

    def test_unknown_provider_fails_clearly(self):
        with pytest.raises(UnknownMirrorProviderError) as ei:
            get_provider("does-not-exist")
        assert "does-not-exist" in str(ei.value)
        assert ei.value.code == "unknown_provider"

    def test_register_custom_provider(self, repo: Path):
        class FakeProvider:
            name = "fake-a2-4"

            def generate(self, request, config):
                return MirrorResult(
                    mirrors=[{"source_file": "x.py", "node_id": "mirror-x"}],
                    provider=self.name,
                    success=True,
                )

        register_provider("fake-a2-4", FakeProvider, replace=True)
        try:
            result = run_mirror_provider(
                MirrorRequest(repo_root=repo, phase=1, source_files=["src/mod.py"]),
                MirrorConfig(provider="fake-a2-4"),
            )
            assert result.provider == "fake-a2-4"
            assert result.success is True
            assert result.mirrors[0]["node_id"] == "mirror-x"
        finally:
            unregister_provider("fake-a2-4")


# ═══════════════════════════════════════════════════════════════════════
#  Legacy regression
# ═══════════════════════════════════════════════════════════════════════


class TestLegacyRegression:
    def test_generate_mirror_default_writes_legacy_mirror(self, repo: Path):
        result = generate_mirror(
            repo,
            phase=1,
            source_files=["src/mod.py"],
        )
        assert result["success"] is True
        assert result["provider"] == "legacy"
        assert result["files_processed"] == 1
        assert len(result["mirrors"]) == 1
        mirror_path = Path(result["mirrors"][0]["mirror_path"])
        assert mirror_path.is_file()
        assert "greet" in mirror_path.read_text(encoding="utf-8")

    def test_generate_mirror_legacy_direct(self, repo: Path):
        result = generate_mirror_legacy(
            repo,
            phase=2,
            source_files=["src/mod.py"],
        )
        assert result["provider"] == "legacy"
        assert result["definitions_total"] >= 1

    def test_generate_mirror_via_config_legacy(self, repo: Path):
        cfg = PropagationConfig(mirror=MirrorConfig(provider="legacy"))
        result = generate_mirror(
            repo,
            phase=1,
            source_files=["src/mod.py"],
            config=cfg,
        )
        assert result["provider"] == "legacy"
        assert result["success"] is True

    def test_refresh_mirror_legacy(self, repo: Path):
        result = refresh_mirror(
            repo,
            phase=1,
            source_files=["src/mod.py"],
            config=MirrorConfig(provider="legacy"),
        )
        assert result["provider"] == "legacy"
        assert "provider_identity" in result


# ═══════════════════════════════════════════════════════════════════════
#  Fallback policy
# ═══════════════════════════════════════════════════════════════════════


class TestFallbackPolicy:
    def test_no_silent_fallback_when_disabled(self, repo: Path):
        class BoomProvider:
            name = "boom"

            def generate(self, request, config):
                raise MirrorProviderError(
                    "intentional failure",
                    provider=self.name,
                    code="boom",
                )

        register_provider("boom", BoomProvider, replace=True)
        try:
            with pytest.raises(MirrorProviderError) as ei:
                run_mirror_provider(
                    MirrorRequest(repo_root=repo, phase=1, source_files=["src/mod.py"]),
                    MirrorConfig(provider="boom", fallback_on_error=False),
                )
            assert ei.value.code == "boom"
            assert "intentional failure" in str(ei.value)
        finally:
            unregister_provider("boom")

    def test_explicit_fallback_to_legacy(self, repo: Path):
        class BoomProvider:
            name = "boom2"

            def generate(self, request, config):
                raise MirrorProviderError(
                    "intentional failure",
                    provider=self.name,
                    code="boom",
                )

        register_provider("boom2", BoomProvider, replace=True)
        try:
            result = run_mirror_provider(
                MirrorRequest(repo_root=repo, phase=1, source_files=["src/mod.py"]),
                MirrorConfig(provider="boom2", fallback_on_error=True),
            )
            assert result.success is True
            assert result.fallback_used is True
            assert result.provider == "legacy"
            assert result.provider_metadata.get("fallback_from") == "boom2"
            assert any(e.get("recovered_via") == "legacy" for e in result.errors)
            assert len(result.mirrors) == 1
        finally:
            unregister_provider("boom2")

    def test_unknown_provider_no_fallback(self, repo: Path):
        with pytest.raises(UnknownMirrorProviderError):
            run_mirror_provider(
                MirrorRequest(repo_root=repo, phase=1),
                MirrorConfig(provider="not-a-real-provider", fallback_on_error=True),
            )

    def test_provider_success_false_with_fallback(self, repo: Path):
        class SoftFail:
            name = "softfail"

            def generate(self, request, config):
                return MirrorResult(
                    success=False,
                    errors=[{"code": "soft", "message": "soft fail"}],
                    provider=self.name,
                )

        register_provider("softfail", SoftFail, replace=True)
        try:
            result = run_mirror_provider(
                MirrorRequest(repo_root=repo, phase=1, source_files=["src/mod.py"]),
                MirrorConfig(provider="softfail", fallback_on_error=True),
            )
            assert result.fallback_used is True
            assert result.provider == "legacy"
        finally:
            unregister_provider("softfail")
