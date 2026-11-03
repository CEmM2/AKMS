from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import akms.repo_wiki.cli as cli_module
import akms.repo_wiki.export as export_package
from akms.repo_wiki.cli import build_parser, main
from akms.repo_wiki.extract.registry import ExtractionResult
from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.models import ParsedModule, SourceFile


GENERATED_AT = "2026-03-07T12:00:00+00:00"


def _argv(repo_root: Path, *extra: str) -> list[str]:
    return [
        "--repo-root",
        str(repo_root),
        "export-akms",
        "--output",
        "akms-output",
        "--phase",
        "1",
        "--generated-at",
        GENERATED_AT,
        *extra,
    ]


def _installed_entry_point() -> Path:
    sibling = Path(sys.executable).with_name("repo-wiki")
    if sibling.is_file():
        return sibling
    raise AssertionError("installed repo-wiki entry point not found")


@pytest.mark.integration
def test_export_akms_json_writes_every_artifact_under_repo_root(tmp_path: Path, capsys):
    source = 'MESSAGE = "hello"\r\n'
    (tmp_path / "message.py").write_bytes(source.encode("utf-8"))

    assert main(_argv(tmp_path, "--full", "--json")) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["export_schema_version"] == 1
    assert payload["generated_at"] == GENERATED_AT
    assert payload["phase"] == 1
    assert payload["errors"] == []
    assert payload["removed"] == []
    assert payload["skipped"] == []
    assert payload["selection"]["mode"] == "full"
    assert payload["selected"] == [
        {
            "language": "python",
            "source_hash": payload["written"][0]["source_hash"],
            "source_path": "message.py",
        }
    ]
    assert payload["written"] == [
        {
            "content_ref": "code-mirror/message.md",
            "generated_path": ".knowledge/code-mirror/message.md",
            "language": "python",
            "node_id": "mirror-message",
            "source_hash": payload["written"][0]["source_hash"],
            "source_path": "message.py",
        }
    ]
    mirror = tmp_path / "akms-output" / payload["written"][0]["generated_path"]
    assert mirror.exists()
    assert source.encode("utf-8") in mirror.read_bytes()


@pytest.mark.integration
def test_changed_only_skips_byte_identical_mirror(tmp_path: Path, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    assert main(_argv(tmp_path, "--full", "--json")) == 0
    capsys.readouterr()

    assert main(_argv(tmp_path, "--changed-only", "--json")) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["written"] == []
    assert payload["skipped"] == [
        {
            "language": "python",
            "reason": "unchanged",
            "source_hash": payload["skipped"][0]["source_hash"],
            "source_path": "pkg/value.py",
        }
    ]


@pytest.mark.integration
def test_strict_parse_failure_is_structured_and_prevents_pruning(
    tmp_path: Path, capsys
):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    stale = tmp_path / "akms-output" / ".knowledge" / "code-mirror" / "stale.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("prior mirror\n", encoding="utf-8")

    assert main(_argv(tmp_path, "--full", "--prune", "--strict-parse", "--json")) == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["written"] == []
    assert payload["removed"] == []
    assert payload["skipped"] == []
    assert payload["errors"][0]["source_path"] == "pkg/broken.py"
    assert payload["errors"][0]["stage"] == "parse"
    assert "broken.py" in captured.err
    assert stale.read_text(encoding="utf-8") == "prior mirror\n"


@pytest.mark.integration
def test_parse_failure_is_skipped_by_default_and_the_rest_exported(
    tmp_path: Path, capsys
):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "pkg" / "ok.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert main(_argv(tmp_path, "--full", "--prune", "--json")) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["errors"] == []
    assert [item["source_path"] for item in payload["written"]] == ["pkg/ok.py"]
    assert [(s["source_path"], s["reason"]) for s in payload["skipped"]] == [
        ("pkg/broken.py", "parse_error")
    ]
    assert "pkg/broken.py" in captured.err
    assert "skipped" in captured.err


@pytest.mark.integration
def test_strict_parse_flag_is_parsed():
    parser = build_parser()
    base = ["--repo-root", ".", "export-akms", "--output", "o", "--phase", "1"]
    assert parser.parse_args(base).strict_parse is False
    assert parser.parse_args([*base, "--strict-parse"]).strict_parse is True


@pytest.mark.integration
def test_undecodable_source_is_error_without_replacement_decoding(
    tmp_path: Path, capsys
):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "bad.py").write_bytes(b"VALUE = '\xff'\n")

    assert main(_argv(tmp_path, "--json")) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"][0]["source_path"] == "pkg/bad.py"
    assert payload["errors"][0]["stage"] == "decode"
    assert not (tmp_path / "akms-output").exists()


@pytest.mark.integration
def test_invalid_timestamp_and_unknown_flag_fail_before_mutation(
    tmp_path: Path, capsys
):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    invalid = _argv(tmp_path, "--generated-at", "not-a-timestamp", "--json")

    assert main(invalid) == 2
    assert not (tmp_path / "akms-output").exists()
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(_argv(tmp_path, "--unknown"))
    assert exc_info.value.code == 2
    assert not (tmp_path / "akms-output").exists()


@pytest.mark.integration
def test_installed_entry_point_accepts_argv_without_shell(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    entry_point = _installed_entry_point()
    env = os.environ.copy()
    source_root = Path(__file__).resolve().parents[2] / "src"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(source_root), env["PYTHONPATH"]]
        if env.get("PYTHONPATH")
        else [str(source_root)]
    )

    completed = subprocess.run(
        [str(entry_point), *_argv(tmp_path, "--json")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["written"][0]["source_path"] == "pkg/value.py"


@pytest.mark.integration
def test_non_json_mode_is_human_readable(tmp_path: Path, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert main(_argv(tmp_path, "--full")) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("written: .knowledge/code-mirror/")
    assert not captured.out.lstrip().startswith("{")
    assert captured.err == ""


@pytest.mark.integration
def test_prune_removes_only_exporter_owned_stale_mirrors(tmp_path: Path, capsys):
    package = tmp_path / "pkg"
    package.mkdir()
    stale_source = package / "stale.py"
    stale_source.write_text("STALE = 1\n", encoding="utf-8")
    assert main(_argv(tmp_path, "--full", "--json")) == 0
    first = json.loads(capsys.readouterr().out)
    stale_mirror = tmp_path / "akms-output" / first["written"][0]["generated_path"]
    unrelated = stale_mirror.parent / "README.md"
    unrelated.write_text("# human-authored\n", encoding="utf-8")

    stale_source.unlink()
    (package / "live.py").write_text("LIVE = 1\n", encoding="utf-8")
    assert main(_argv(tmp_path, "--full", "--prune", "--json")) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [item["source_path"] for item in payload["removed"]] == ["pkg/stale.py"]
    assert not stale_mirror.exists()
    assert unrelated.read_text(encoding="utf-8") == "# human-authored\n"


@pytest.mark.integration
def test_partial_write_failure_preserves_stale_mirror_and_skips_prune(
    tmp_path: Path, capsys, monkeypatch
):
    package = tmp_path / "pkg"
    package.mkdir()
    stale_source = package / "stale.py"
    stale_source.write_text("STALE = 1\n", encoding="utf-8")
    assert main(_argv(tmp_path, "--full", "--json")) == 0
    first = json.loads(capsys.readouterr().out)
    stale_mirror = tmp_path / "akms-output" / first["written"][0]["generated_path"]

    stale_source.unlink()
    (package / "fails.py").write_text("FAILS = 1\n", encoding="utf-8")
    (package / "works.py").write_text("WORKS = 1\n", encoding="utf-8")
    real_atomic_write = export_package.atomic_write_text

    def fail_one_write(path: Path, content: str) -> None:
        if path.name == "fails.md":
            raise OSError("injected write failure")
        real_atomic_write(path, content)

    monkeypatch.setattr(export_package, "atomic_write_text", fail_one_write)

    assert main(_argv(tmp_path, "--full", "--prune", "--json")) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"][0]["stage"] == "write"
    assert [item["source_path"] for item in payload["written"]] == ["pkg/works.py"]
    assert payload["removed"] == []
    assert stale_mirror.exists()


@pytest.mark.integration
def test_export_rebinds_project_backend_placeholder_source_metadata(
    tmp_path: Path, capsys, monkeypatch
):
    source_path = "value.cpp"
    source_text = "int value() { return 1; }\n"
    absolute = tmp_path / source_path
    absolute.parent.mkdir(exist_ok=True)
    absolute.write_text(source_text, encoding="utf-8")
    config = tmp_path / ".repo_wiki" / "config.yaml"
    config.parent.mkdir()
    config.write_text("languages:\n  cpp:\n    enabled: true\n", encoding="utf-8")

    def placeholder_extraction(
        sources: list[SourceFile], _config: dict[str, object]
    ) -> ExtractionResult:
        assert [source.path for source in sources] == [source_path]
        placeholder = SourceFile(source_path, str(absolute), "cpp", 0, "")
        return ExtractionResult(
            parsed_modules={
                source_path: ParsedModule(placeholder, "value", None, [], [])
            },
            handled_languages={"cpp"},
        )

    monkeypatch.setattr(export_package, "extract_files", placeholder_extraction)

    assert main(_argv(tmp_path, "--full", "--json")) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"] == []
    assert payload["written"][0]["language"] == "cpp"
    assert payload["written"][0]["source_hash"] == sha256_text(source_text)


@pytest.mark.integration
def test_unexpected_backend_failure_is_clean_structured_cli_error(
    tmp_path: Path, capsys, monkeypatch
):
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")

    def fail_export(**_kwargs):
        raise RuntimeError("injected backend failure")

    monkeypatch.setattr(cli_module, "export_akms", fail_export)

    assert main(_argv(tmp_path, "--json")) == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["errors"] == [
        {
            "language": None,
            "message": "injected backend failure",
            "source_path": None,
            "stage": "validation",
        }
    ]
    assert "injected backend failure" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.unit
def test_help_states_export_does_not_summarize_or_index(capsys):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["export-akms", "--help"])
    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "does not summarize or index" in help_text


@pytest.mark.integration
def test_json_stdout_has_stable_keys_and_diagnostics_stay_on_stderr(
    tmp_path: Path, capsys
):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    assert main(_argv(tmp_path, "--strict-parse", "--json")) == 1

    captured = capsys.readouterr()
    assert set(json.loads(captured.out)) == {
        "export_schema_version",
        "phase",
        "generated_at",
        "selection",
        "selected",
        "written",
        "removed",
        "skipped",
        "errors",
    }
    assert "pkg/broken.py" in captured.err


@pytest.mark.integration
def test_knowledge_dir_defaults_to_dot_knowledge(tmp_path: Path, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert main(_argv(tmp_path, "--full", "--json")) == 0

    [written] = json.loads(capsys.readouterr().out)["written"]
    assert written["generated_path"] == ".knowledge/code-mirror/pkg/value.md"
    # content_ref is relative to the knowledge directory, so it is unchanged.
    assert written["content_ref"] == "code-mirror/pkg/value.md"
    assert (tmp_path / "akms-output" / written["generated_path"]).is_file()
    assert not (tmp_path / "akms-output" / "knowledge").exists()


@pytest.mark.integration
def test_knowledge_dir_option_writes_under_legacy_knowledge(tmp_path: Path, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")

    argv = _argv(tmp_path, "--full", "--json", "--knowledge-dir", "knowledge")
    assert main(argv) == 0

    [written] = json.loads(capsys.readouterr().out)["written"]
    assert written["generated_path"] == "knowledge/code-mirror/pkg/value.md"
    assert written["content_ref"] == "code-mirror/pkg/value.md"
    assert not (tmp_path / "akms-output" / ".knowledge").exists()


@pytest.mark.integration
def test_knowledge_dir_option_rejects_other_names(tmp_path: Path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(_argv(tmp_path, "--full", "--knowledge-dir", "../elsewhere"))

    assert exit_info.value.code == 2
    assert "--knowledge-dir" in capsys.readouterr().err


@pytest.mark.integration
def test_prune_only_touches_the_selected_knowledge_dir(tmp_path: Path, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "old.py").write_text("OLD = 1\n", encoding="utf-8")
    argv = _argv(tmp_path, "--full", "--json", "--knowledge-dir", "knowledge")
    assert main(argv) == 0
    legacy_old = tmp_path / "akms-output" / "knowledge" / "code-mirror" / "pkg"
    assert (legacy_old / "old.md").is_file()
    (tmp_path / "pkg" / "old.py").unlink()
    capsys.readouterr()

    assert main(_argv(tmp_path, "--full", "--prune", "--json")) == 0

    assert json.loads(capsys.readouterr().out)["removed"] == []
    assert (legacy_old / "old.md").is_file()
