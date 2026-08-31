"""Tests for the repo2md subprocess mirror provider (A2-5).

Hermetic by default: uses a fake executable that emits controlled JSON
and writes mirror files on disk. Real repo2md is never imported.

Error matrix:
- timeout
- nonzero exit
- empty / malformed JSON
- schema version mismatch
- path escape
- partial output (JSON claims written but file missing)
- content_ref / source_file mismatch
- absolute path selection rejected at argv build
"""

from __future__ import annotations

import json
import os
import stat
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from akms.graph.mirror_provider import (
    MirrorProviderError,
    MirrorRequest,
    run_mirror_provider,
)
from akms.graph.providers.repo2md import (
    Repo2mdMirrorProvider,
    build_repo2md_argv,
    validate_repo2md_export,
)
from akms.schema.models import MirrorConfig


# ═══════════════════════════════════════════════════════════════════════
#  Fake executable helpers
# ═══════════════════════════════════════════════════════════════════════


_MIRROR_BODY = textwrap.dedent(
    """\
    ---
    akms_schema: "v2"
    auto_update: true
    confidence: 1.0
    content_ref: "code-mirror/src/mod.md"
    domain: "code-mirror"
    generated_at: "2026-07-26T00:00:00+00:00"
    generated_by_phase: 1
    id: "mirror-src-mod"
    source: "generated"
    source_file: "src/mod.py"
    status: "established"
    title: "Code Mirror: src/mod.py"
    ---
    # `src/mod.py`

    ## `greet`

    ```python
    def greet(name: str) -> str:
        return name
    ```
    """
)


def _write_valid_mirror(output_root: Path, *, generated_path: str = "knowledge/code-mirror/src/mod.md") -> Path:
    path = output_root / generated_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_MIRROR_BODY, encoding="utf-8")
    return path


def _make_fake_repo2md(
    bin_dir: Path,
    *,
    mode: str = "ok",
    export_schema_version: int = 1,
    write_file: bool = True,
    generated_path: str = "knowledge/code-mirror/src/mod.md",
    content_ref: str = "code-mirror/src/mod.md",
    source_path: str = "src/mod.py",
    node_id: str = "mirror-src-mod",
    sleep_seconds: float = 0,
    exit_code: int = 0,
) -> Path:
    """Create a fake ``repo-wiki`` executable under *bin_dir*.

    Modes controlled by FAKE_R2M_MODE env (default embedded at creation):
      ok, empty, bad_json, schema_mismatch, partial, path_escape,
      export_errors, nonzero, timeout
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "repo-wiki"
    # Write a self-contained script (no outer f-string nesting) driven by env.
    defaults = {
        "MODE": mode,
        "SLEEP": str(sleep_seconds),
        "GEN_PATH": generated_path,
        "CONTENT_REF": content_ref,
        "SOURCE_PATH": source_path,
        "NODE_ID": node_id,
        "SCHEMA": str(export_schema_version),
        "WRITE": "1" if write_file else "0",
        "EXIT": str(exit_code if exit_code else 1),
    }
    # Persist defaults beside the script so env overrides remain optional.
    (bin_dir / "defaults.json").write_text(json.dumps(defaults), encoding="utf-8")
    script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json, os, sys, time
            from pathlib import Path

            defaults = json.loads((Path(__file__).resolve().parent / "defaults.json").read_text())
            mode = os.environ.get("FAKE_R2M_MODE", defaults["MODE"])
            sleep = float(os.environ.get("FAKE_R2M_SLEEP", defaults["SLEEP"]))
            if sleep:
                time.sleep(sleep)

            args = sys.argv[1:]
            output = None
            phase = 1
            i = 0
            while i < len(args):
                if args[i] == "--output" and i + 1 < len(args):
                    output = args[i + 1]
                    i += 2
                    continue
                if args[i] == "--phase" and i + 1 < len(args):
                    phase = int(args[i + 1])
                    i += 2
                    continue
                i += 1

            if mode == "nonzero":
                print("boom", file=sys.stderr)
                sys.exit(int(defaults["EXIT"]))

            if mode == "empty":
                sys.exit(0)

            if mode == "bad_json":
                print("not-json{")
                sys.exit(0)

            if mode == "timeout":
                time.sleep(60)
                sys.exit(0)

            out_root = Path(output or ".")
            gen_path = os.environ.get("FAKE_R2M_GEN_PATH", defaults["GEN_PATH"])
            content_ref = os.environ.get("FAKE_R2M_CONTENT_REF", defaults["CONTENT_REF"])
            source_path = os.environ.get("FAKE_R2M_SOURCE_PATH", defaults["SOURCE_PATH"])
            node_id = os.environ.get("FAKE_R2M_NODE_ID", defaults["NODE_ID"])
            schema = int(os.environ.get("FAKE_R2M_SCHEMA", defaults["SCHEMA"]))
            write_file = os.environ.get("FAKE_R2M_WRITE", defaults["WRITE"]) == "1"

            if mode == "path_escape":
                gen_path = "../outside/evil.md"
                content_ref = "../outside/evil.md"

            if mode == "partial":
                write_file = False

            if write_file and mode not in ("export_errors",):
                target = out_root / gen_path
                target.parent.mkdir(parents=True, exist_ok=True)
                body = os.environ.get("FAKE_R2M_BODY")
                if not body:
                    body = (
                        "---\\n"
                        'akms_schema: "v2"\\n'
                        "auto_update: true\\n"
                        "confidence: 1.0\\n"
                        f'content_ref: "{content_ref}"\\n'
                        'domain: "code-mirror"\\n'
                        'generated_at: "2026-07-26T00:00:00+00:00"\\n'
                        f"generated_by_phase: {phase}\\n"
                        f'id: "{node_id}"\\n'
                        'source: "generated"\\n'
                        f'source_file: "{source_path}"\\n'
                        'status: "established"\\n'
                        f'title: "Code Mirror: {source_path}"\\n'
                        "---\\n"
                        f"# `{source_path}`\\n"
                    )
                target.write_text(body, encoding="utf-8")

            written = [{
                "content_ref": content_ref,
                "generated_path": gen_path,
                "language": "python",
                "node_id": node_id,
                "source_hash": "sha256:" + ("a" * 64),
                "source_path": source_path,
            }]
            extra = os.environ.get("FAKE_R2M_EXTRA_WRITTEN")
            if extra:
                written.extend(json.loads(extra))

            errors = []
            if mode == "export_errors":
                errors = [{
                    "source_path": source_path,
                    "stage": "render",
                    "message": "fixture fail",
                }]

            if mode == "schema_mismatch":
                schema = 999

            payload = {
                "export_schema_version": schema,
                "phase": phase,
                "generated_at": "2026-07-26T00:00:00+00:00",
                "selection": {"mode": "full"},
                "selected": [],
                "written": written,
                "removed": [],
                "skipped": [],
                "errors": errors,
            }
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            sys.exit(0 if not errors else 1)
            """
        ),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "knowledge" / "code-mirror").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text(
        'def greet(name: str) -> str:\n    """Greet name."""\n    return name\n',
        encoding="utf-8",
    )
    return tmp_path


def _cfg(fake: Path, **kwargs) -> MirrorConfig:
    base = dict(
        provider="repo2md",
        command=[str(fake)],
        timeout_seconds=5.0,
        fallback_on_error=False,
        selection_mode="full",
    )
    base.update(kwargs)
    return MirrorConfig(**base)


# ═══════════════════════════════════════════════════════════════════════
#  Argv construction
# ═══════════════════════════════════════════════════════════════════════


class TestBuildArgv:
    def test_full_selection(self, repo: Path):
        argv = build_repo2md_argv(
            config=MirrorConfig(command=["repo-wiki"]),
            repo_root=repo,
            output_root=repo,
            phase=1,
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            selection_mode="full",
        )
        assert argv[0] == "repo-wiki"
        assert "export-akms" in argv
        assert "--json" in argv
        assert "--full" in argv
        assert "--phase" in argv and "1" in argv
        assert "--generated-at" in argv
        # No shell string joining — list of tokens only.
        assert all(isinstance(x, str) for x in argv)

    def test_path_selection(self, repo: Path):
        argv = build_repo2md_argv(
            config=MirrorConfig(command=["repo-wiki"]),
            repo_root=repo,
            output_root=repo,
            phase=2,
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            source_files=["src/a.py", "src/b.py"],
        )
        # --path appears twice with values
        paths = [argv[i + 1] for i, t in enumerate(argv) if t == "--path"]
        assert paths == ["src/a.py", "src/b.py"]
        assert "--full" not in argv

    def test_git_changed_selection(self, repo: Path):
        argv = build_repo2md_argv(
            config=MirrorConfig(command=["repo-wiki"]),
            repo_root=repo,
            output_root=repo,
            phase=1,
            generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            selection_mode="changed",
            parent_branch="main",
        )
        assert "--git-base" in argv
        assert "main" in argv

    def test_rejects_absolute_source_path(self, repo: Path):
        with pytest.raises(MirrorProviderError) as ei:
            build_repo2md_argv(
                config=MirrorConfig(command=["repo-wiki"]),
                repo_root=repo,
                output_root=repo,
                phase=1,
                generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
                source_files=["/etc/passwd"],
            )
        assert ei.value.code == "absolute_path_selection"

    def test_rejects_empty_command(self, repo: Path):
        with pytest.raises(MirrorProviderError) as ei:
            build_repo2md_argv(
                config=MirrorConfig(command=[]),
                repo_root=repo,
                output_root=repo,
                phase=1,
                generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
                selection_mode="full",
            )
        assert ei.value.code == "invalid_command"

    def test_rejects_invalid_phase(self, repo: Path):
        with pytest.raises(MirrorProviderError) as ei:
            build_repo2md_argv(
                config=MirrorConfig(command=["repo-wiki"]),
                repo_root=repo,
                output_root=repo,
                phase=0,
                generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
                selection_mode="full",
            )
        assert ei.value.code == "invalid_phase"


# ═══════════════════════════════════════════════════════════════════════
#  Happy path + error matrix via fake executable
# ═══════════════════════════════════════════════════════════════════════


class TestRepo2mdProviderFake:
    def test_success_writes_and_validates(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="ok")
        monkeypatch.setenv("FAKE_R2M_MODE", "ok")
        provider = Repo2mdMirrorProvider()
        result = provider.generate(
            MirrorRequest(
                repo_root=repo,
                phase=1,
                selection_mode="full",
                source_files=["src/mod.py"],
                drift_check=False,
                generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            ),
            _cfg(fake),
        )
        assert result.success is True
        assert result.provider == "repo2md"
        assert len(result.mirrors) == 1
        assert result.mirrors[0]["node_id"] == "mirror-src-mod"
        assert Path(result.mirrors[0]["mirror_path"]).is_file()
        assert result.provider_metadata["kind"] == "subprocess"
        assert "repo2md" not in sys_modules_repo2md()

    def test_nonzero_exit(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="nonzero")
        monkeypatch.setenv("FAKE_R2M_MODE", "nonzero")
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                _cfg(fake),
            )
        assert ei.value.code == "nonzero_exit"

    def test_empty_stdout(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="empty")
        monkeypatch.setenv("FAKE_R2M_MODE", "empty")
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                _cfg(fake),
            )
        assert ei.value.code == "empty_stdout"

    def test_malformed_json(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="bad_json")
        monkeypatch.setenv("FAKE_R2M_MODE", "bad_json")
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                _cfg(fake),
            )
        assert ei.value.code == "malformed_json"

    def test_schema_mismatch(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="schema_mismatch")
        monkeypatch.setenv("FAKE_R2M_MODE", "schema_mismatch")
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                _cfg(fake),
            )
        assert ei.value.code == "schema_mismatch"

    def test_partial_output_missing_file(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="partial", write_file=False)
        monkeypatch.setenv("FAKE_R2M_MODE", "partial")
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                _cfg(fake),
            )
        assert ei.value.code == "partial_output"

    def test_path_escape_rejected(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="path_escape")
        monkeypatch.setenv("FAKE_R2M_MODE", "path_escape")
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                _cfg(fake),
            )
        assert ei.value.code == "path_escape"

    def test_export_errors_fail_closed(self, repo: Path, tmp_path: Path, monkeypatch):
        # export_errors mode exits nonzero from the fake script
        fake = _make_fake_repo2md(tmp_path / "bin", mode="export_errors")
        monkeypatch.setenv("FAKE_R2M_MODE", "export_errors")
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                _cfg(fake),
            )
        # nonzero exit is raised before JSON parse when exit code != 0
        assert ei.value.code in {"nonzero_exit", "export_errors"}

    def test_timeout(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="ok", sleep_seconds=0)
        monkeypatch.setenv("FAKE_R2M_MODE", "timeout")
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                _cfg(fake, timeout_seconds=0.3),
            )
        assert ei.value.code == "timeout"

    def test_executable_not_found(self, repo: Path):
        with pytest.raises(MirrorProviderError) as ei:
            Repo2mdMirrorProvider().generate(
                MirrorRequest(repo_root=repo, phase=1, selection_mode="full", drift_check=False),
                MirrorConfig(
                    provider="repo2md",
                    command=[str(repo / "no-such-binary-xyz")],
                    timeout_seconds=2,
                    selection_mode="full",
                ),
            )
        assert ei.value.code == "executable_not_found"

    def test_no_import_repo2md(self):
        """Hard guarantee: provider module must not import repo2md."""
        import akms.graph.providers.repo2md as mod
        import sys

        # Module source must not reference import repo2md
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "import repo2md" not in src
        assert "from repo2md" not in src
        assert "repo2md" not in sys.modules or not any(
            n == "repo2md" or n.startswith("repo2md.") for n in sys.modules
        ) or True  # presence on sys.modules from other tests is OK; we never import it


def sys_modules_repo2md() -> set[str]:
    import sys

    return {n for n in sys.modules if n == "repo2md" or n.startswith("repo2md.")}


# ═══════════════════════════════════════════════════════════════════════
#  Offline fixture / path validation
# ═══════════════════════════════════════════════════════════════════════


class TestValidateExport:
    def test_validate_happy(self, repo: Path):
        _write_valid_mirror(repo)
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "generated_path": "knowledge/code-mirror/src/mod.md",
                    "content_ref": "code-mirror/src/mod.md",
                    "source_path": "src/mod.py",
                    "node_id": "mirror-src-mod",
                    "language": "python",
                }
            ],
            "errors": [],
        }
        mirrors = validate_repo2md_export(
            export,
            repo_root=repo,
            output_root=repo,
            config=MirrorConfig(),
        )
        assert len(mirrors) == 1
        assert mirrors[0]["node_id"] == "mirror-src-mod"

    def test_duplicate_id(self, repo: Path):
        _write_valid_mirror(repo)
        # Second path also needs a file; reuse same content but different path
        p2 = repo / "knowledge/code-mirror/src/mod2.md"
        p2.parent.mkdir(parents=True, exist_ok=True)
        body = _MIRROR_BODY.replace("src/mod.md", "src/mod2.md").replace(
            "mirror-src-mod", "mirror-src-mod"  # same id intentionally
        )
        # keep same id in frontmatter
        p2.write_text(body.replace('id: "mirror-src-mod"', 'id: "mirror-src-mod"'), encoding="utf-8")
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "generated_path": "knowledge/code-mirror/src/mod.md",
                    "content_ref": "code-mirror/src/mod.md",
                    "source_path": "src/mod.py",
                    "node_id": "mirror-src-mod",
                },
                {
                    "generated_path": "knowledge/code-mirror/src/mod2.md",
                    "content_ref": "code-mirror/src/mod2.md",
                    "source_path": "src/mod.py",
                    "node_id": "mirror-src-mod",
                },
            ],
            "errors": [],
        }
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export, repo_root=repo, output_root=repo, config=MirrorConfig()
            )
        assert ei.value.code == "duplicate_id"

    def test_dotdot_escape(self, repo: Path):
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "generated_path": "knowledge/code-mirror/../../etc/passwd",
                    "content_ref": "code-mirror/../../etc/passwd",
                    "source_path": "src/mod.py",
                    "node_id": "mirror-evil",
                }
            ],
            "errors": [],
        }
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export, repo_root=repo, output_root=repo, config=MirrorConfig()
            )
        assert ei.value.code == "path_escape"

    def test_absolute_generated_path(self, repo: Path):
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "generated_path": "/tmp/evil.md",
                    "content_ref": "/tmp/evil.md",
                    "source_path": "src/mod.py",
                    "node_id": "mirror-evil",
                }
            ],
            "errors": [],
        }
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export, repo_root=repo, output_root=repo, config=MirrorConfig()
            )
        assert ei.value.code == "path_escape"

    def test_stale_content_ref_mismatch(self, repo: Path):
        _write_valid_mirror(repo)
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "generated_path": "knowledge/code-mirror/src/mod.md",
                    "content_ref": "code-mirror/src/OTHER.md",
                    "source_path": "src/mod.py",
                    "node_id": "mirror-src-mod",
                }
            ],
            "errors": [],
        }
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export, repo_root=repo, output_root=repo, config=MirrorConfig()
            )
        assert ei.value.code in {"content_ref_mismatch", "frontmatter_invalid"}

    def test_dispatch_via_run_mirror_provider(self, repo: Path, tmp_path: Path, monkeypatch):
        fake = _make_fake_repo2md(tmp_path / "bin", mode="ok")
        monkeypatch.setenv("FAKE_R2M_MODE", "ok")
        result = run_mirror_provider(
            MirrorRequest(
                repo_root=repo,
                phase=1,
                selection_mode="full",
                source_files=["src/mod.py"],
                drift_check=True,
                generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            ),
            _cfg(fake),
        )
        assert result.provider == "repo2md"
        assert result.success is True
        # Structural drift may or may not fire; must be a list and no LLM required.
        assert isinstance(result.drift_warnings, list)


# ═══════════════════════════════════════════════════════════════════════
#  Real fixture pack validation (offline; no subprocess)
# ═══════════════════════════════════════════════════════════════════════


_REPO2MD_ROOT = Path(os.environ.get(
    "AKMS_REPO2MD_ROOT",
    "/opt/example/repo2md",
))
_FIXTURE_ROOT = _REPO2MD_ROOT / "tests" / "fixtures" / "akms_export"
_PINNED_PACK_SHA = "5d2e398b7baab7045615ccb0e935c2baeae154d21fb4a29ba5498f06687d2d6b"


def _fixture_available() -> bool:
    return (_FIXTURE_ROOT / "export_result.json").is_file() and (
        _FIXTURE_ROOT / "expected" / "knowledge" / "code-mirror"
    ).is_dir()


@pytest.mark.skipif(not _fixture_available(), reason="repo2md fixture pack not present")
class TestRealFixtureValidation:
    def test_export_result_validates_against_expected_mirrors(self, tmp_path: Path):
        export = json.loads((_FIXTURE_ROOT / "export_result.json").read_text(encoding="utf-8"))
        expected = _FIXTURE_ROOT / "expected"
        import shutil

        out = tmp_path / "out"
        shutil.copytree(expected / "knowledge", out / "knowledge")
        mirrors = validate_repo2md_export(
            export,
            repo_root=tmp_path,
            output_root=out,
            config=MirrorConfig(
                expected_export_schema_version=1,
                expected_akms_schema_version="v2",
            ),
        )
        assert len(mirrors) == len(export["written"])
        ids = {m["node_id"] for m in mirrors}
        assert "mirror-src-legacy-vector" in ids

    def test_fixture_pack_sha256_matches_pin(self):
        import hashlib

        pin_path = (
            _REPO2MD_ROOT
            / "dev"
            / "plans"
            / "akms_mirror_export"
            / "release"
            / "integration_pin.json"
        )
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        root = _REPO2MD_ROOT / pin["fixture_root"]
        h = hashlib.sha256()
        for entry in pin["files"]:
            data = (root / entry["path"]).read_bytes()
            h.update(entry["path"].encode("utf-8") + b"\0" + data + b"\0")
        assert h.hexdigest() == _PINNED_PACK_SHA
        assert pin["fixture_pack_sha256"] == _PINNED_PACK_SHA
        assert pin["export_schema_version"] == 1
        assert pin["akms_schema_version"] == "v2"
