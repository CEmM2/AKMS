"""Manifest schema migration and per-symbol source hashing."""

from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path

import pytest

from akms.repo_wiki.manifest import (
    MANIFEST_PATH,
    SCHEMA_VERSION,
    _is_v1,
    _migrate_v1_to_v2,
    load_manifest,
    save_manifest,
)
from akms.repo_wiki.models import Language
from akms.repo_wiki.paths import safe_doc_name
from akms.repo_wiki.symbol_ids import build_symbol_id

_TINY_REPO = Path(__file__).parent / "fixtures" / "tiny_repo"


def _v1_manifest() -> dict:
    """Return a representative v1 manifest dict (no schema_version)."""
    return {
        "repo": {"name": "example", "last_commit": "abc1234"},
        "files": {
            "pkg/core.py": {
                "language": "python",
                "hash": "sha256:" + "a" * 64,
                "module_doc": ".repo_wiki/generated/modules/pkg.core.md",
                "summary_hash": None,
                "index_hash": None,
                "symbols": {
                    "pkg.core.Greeter": {
                        "kind": "class",
                        "hash": "sha256:" + "b" * 64,
                        "doc": ".repo_wiki/generated/symbols/pkg.core.Greeter.md",
                        "start_line": 1,
                        "end_line": 10,
                    },
                    "pkg.core.Greeter.greet": {
                        "kind": "method",
                        "hash": "sha256:" + "c" * 64,
                        "doc": ".repo_wiki/generated/symbols/pkg.core.Greeter.greet.md",
                        "start_line": 4,
                        "end_line": 6,
                    },
                },
            },
            "pkg/utils.py": {
                "language": "python",
                "hash": "sha256:" + "d" * 64,
                "module_doc": ".repo_wiki/generated/modules/pkg.utils.md",
                "summary_hash": None,
                "index_hash": None,
                "symbols": {
                    "pkg.utils.helper": {
                        "kind": "function",
                        "hash": "sha256:" + "e" * 64,
                        "doc": ".repo_wiki/generated/symbols/pkg.utils.helper.md",
                        "start_line": 1,
                        "end_line": 3,
                    },
                },
            },
        },
    }


def _write_v1_manifest(repo_root, data: dict) -> None:
    path = repo_root / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_v1_manifest_loaded_and_migrated_on_build(tmp_path):
    """V1 manifest (no schema_version) is detected and migrated to v2."""
    v1 = _v1_manifest()
    assert _is_v1(v1) is True

    migrated = _migrate_v1_to_v2(v1)
    assert migrated["schema_version"] == SCHEMA_VERSION

    id_pattern = re.compile(r"^python:[^:]+::.+$")
    found = False
    for _, file_entry in migrated["files"].items():
        for sym_id in file_entry["symbols"]:
            assert id_pattern.match(sym_id), (
                f"Migrated symbol ID {sym_id!r} does not match generalized form"
            )
            found = True
    assert found, "Expected at least one migrated symbol ID"

    _write_v1_manifest(tmp_path, v1)
    manifest = load_manifest(tmp_path)
    for mf in manifest.files.values():
        for sym_id in mf.symbols:
            assert id_pattern.match(sym_id), (
                f"load_manifest returned non-migrated id {sym_id!r}"
            )


def test_migration_preserves_files_and_hashes(tmp_path):
    """After v1→v2 migration, same files tracked with same hashes."""
    v1 = _v1_manifest()
    migrated = _migrate_v1_to_v2(v1)

    assert set(migrated["files"].keys()) == set(v1["files"].keys())

    for relpath, v1_file in v1["files"].items():
        mig_file = migrated["files"][relpath]
        assert mig_file["hash"] == v1_file["hash"], f"file_hash changed for {relpath!r}"
        assert len(mig_file["symbols"]) == len(v1_file["symbols"])

        old_hashes = sorted(s["hash"] for s in v1_file["symbols"].values())
        new_hashes = sorted(s["hash"] for s in mig_file["symbols"].values())
        assert old_hashes == new_hashes, f"per-symbol hashes changed for {relpath!r}"

        old_by_qual = {}
        module_dotted = relpath.replace("/", ".").rsplit(".py", 1)[0]
        for old_id, sym in v1_file["symbols"].items():
            qual = old_id[len(module_dotted) + 1 :]
            old_by_qual[qual] = sym
        for new_id, sym in mig_file["symbols"].items():
            qual = new_id.split("::", 1)[1]
            old = old_by_qual[qual]
            assert sym["kind"] == old["kind"]
            assert sym["start_line"] == old["start_line"]
            assert sym["end_line"] == old["end_line"]
            assert sym["hash"] == old["hash"]


def test_migration_is_one_shot_subsequent_runs_v2_only(tmp_path):
    """V2 manifest is not re-migrated; subsequent runs operate on v2 only."""
    v1 = _v1_manifest()
    once = _migrate_v1_to_v2(copy.deepcopy(v1))
    twice = _migrate_v1_to_v2(copy.deepcopy(v1))
    assert once == twice

    assert _is_v1(once) is False
    assert _is_v1({"schema_version": 2}) is False
    assert _is_v1({"schema_version": "2"}) is False

    _write_v1_manifest(tmp_path, v1)
    manifest = load_manifest(tmp_path)
    save_manifest(tmp_path, manifest)
    on_disk = json.loads((tmp_path / MANIFEST_PATH).read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == SCHEMA_VERSION
    assert _is_v1(on_disk) is False
    manifest2 = load_manifest(tmp_path)
    ids_pass1 = {sid for mf in manifest.files.values() for sid in mf.symbols}
    ids_pass2 = {sid for mf in manifest2.files.values() for sid in mf.symbols}
    assert ids_pass1 == ids_pass2


def test_migration_rewrites_ids_to_generalized_form(tmp_path):
    """V1 manifest IDs are rewritten to generalized form."""
    v1 = _v1_manifest()
    migrated = _migrate_v1_to_v2(v1)

    expected_ids = {
        "pkg/core.py": {
            build_symbol_id(Language.PYTHON, "pkg/core.py", "Greeter"),
            build_symbol_id(Language.PYTHON, "pkg/core.py", "Greeter.greet"),
        },
        "pkg/utils.py": {
            build_symbol_id(Language.PYTHON, "pkg/utils.py", "helper"),
        },
    }
    assert "python:pkg/core.py::Greeter" in migrated["files"]["pkg/core.py"]["symbols"]
    assert (
        "python:pkg/core.py::Greeter.greet"
        in migrated["files"]["pkg/core.py"]["symbols"]
    )
    assert "python:pkg/utils.py::helper" in migrated["files"]["pkg/utils.py"]["symbols"]

    for relpath, expected in expected_ids.items():
        got = set(migrated["files"][relpath]["symbols"].keys())
        assert got == expected, f"{relpath}: expected {expected!r}, got {got!r}"


def test_migration_recomputes_filenames_via_safe_doc_name(tmp_path):
    """Document filenames are recomputed via safe_doc_name during migration."""
    v1 = _v1_manifest()
    migrated = _migrate_v1_to_v2(v1)

    for file_entry in migrated["files"].values():
        for new_id, sym in file_entry["symbols"].items():
            expected_doc = f"symbols/{safe_doc_name(new_id)}.md"
            assert sym["doc"] == expected_doc, (
                f"symbol {new_id!r}: doc={sym['doc']!r}, expected {expected_doc!r}"
            )


def test_build_repo_produces_symbol_hashes(tmp_path):
    """Every per-symbol hash in a built manifest is a full sha256 digest."""
    from akms.repo_wiki.manifest import build_repo, load_manifest

    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    shutil.copy(_TINY_REPO / "pkg" / "__init__.py", pkg_dir / "__init__.py")
    shutil.copy(_TINY_REPO / "pkg" / "core.py", pkg_dir / "core.py")

    config_dir = tmp_path / ".repo_wiki"
    config_dir.mkdir()
    (tmp_path / "repo2md.yaml").write_text(
        "scanner:\n  include: ['pkg']\n  exclude: []\n"
        "generation:\n  output_dir: .repo_wiki/generated\n"
        "summaries:\n  enabled: false\n",
        encoding="utf-8",
    )

    summary = build_repo(tmp_path, no_summaries=True, no_index=True)
    assert summary.parsed > 0, "Expected at least one parsed module."

    manifest = load_manifest(tmp_path)
    assert manifest.files, "Manifest must contain at least one file entry."

    sha256_re = __import__("re").compile(r"^sha256:[0-9a-f]{64}$")
    for rel_path, mf in manifest.files.items():
        for sym_id, sym_data in mf.symbols.items():
            h = sym_data.get("hash", "")
            assert isinstance(h, str) and sha256_re.match(h), (
                f"Symbol {sym_id!r} in {rel_path!r} has invalid hash: {h!r}. "
                "Expected format 'sha256:<64 hex chars>'."
            )


def test_build_repo_raises_on_missing_source(tmp_path):
    """build_repo raises FileNotFoundError when a symbol's source file is gone at hash time."""
    import hashlib
    from unittest.mock import patch

    from akms.repo_wiki.manifest import build_repo
    from akms.repo_wiki.models import SourceFile
    from akms.repo_wiki.extract.python_ast import parse_python_file as _ppf

    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    core = pkg_dir / "core.py"
    core.write_text(
        '"""Module."""\n\ndef greet(name: str) -> str:\n    return f"Hi {name}"\n',
        encoding="utf-8",
    )

    (tmp_path / "repo2md.yaml").write_text(
        "scanner:\n  include: ['pkg']\n  exclude: []\n"
        "generation:\n  output_dir: .repo_wiki/generated\n"
        "summaries:\n  enabled: false\n",
        encoding="utf-8",
    )

    content = core.read_bytes()
    sf = SourceFile(
        path="pkg/core.py",
        abs_path=str(core),
        language="python",
        size_bytes=len(content),
        content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
    )
    pre_parsed = _ppf(sf)

    core.unlink()

    # Patch so build_repo uses our pre-parsed module without re-scanning.
    # build_repo now routes extraction through the registry, so inject the
    # pre-parsed module via extract_files' ExtractionResult (the seam the
    # direct parse_python_file call used to provide).
    from akms.repo_wiki.extract.registry import ExtractionResult

    injected = ExtractionResult(
        parsed_modules={sf.path: pre_parsed},
        notes=[],
        handled_languages={"python"},
    )
    with (
        patch("akms.repo_wiki.manifest.scan_repository", return_value=([sf], [])),
        patch("akms.repo_wiki.manifest.extract_files", return_value=injected),
    ):
        with pytest.raises(FileNotFoundError) as exc_info:
            build_repo(tmp_path, no_summaries=True, no_index=True)

    msg = str(exc_info.value)
    assert len(msg) > 0, "FileNotFoundError must have a non-empty message."
    assert "core.py" in msg or "Source file not found" in msg, (
        f"FileNotFoundError should identify the missing file. Got: {msg!r}"
    )
