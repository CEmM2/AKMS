"""Tests for ``akms vault status`` and ``akms vault install``.

The install path writes to the user's global vault, which every other part of
AKMS treats as read-only. So the refusals matter as much as the happy path:
each one below is a case where installing anyway would either destroy a vault
the user curated or fill it with files the graph compiler cannot parse.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from akms.cli.commands import build_parser
from akms.cli.vault_commands import _count_nodes

pytestmark = pytest.mark.unit


NODE = """---
akms_schema: v2
id: {nid}
title: {nid}
domain: testing
tags:
- testing
status: established
confidence: 0.9
source: human
context_size: small
reading_priority: full
---

Body for {nid}.
"""


def _make_vault(root: Path, count: int = 3) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (root / f"node-{i}.md").write_text(
            NODE.format(nid=f"node-{i}"), encoding="utf-8"
        )
    payload = root / "content" / "skill"
    payload.mkdir(parents=True)
    (payload / "REFERENCE.md").write_text("# payload\n", encoding="utf-8")
    return root


def _run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


# ── counting ────────────────────────────────────────────────────────────


def test_count_ignores_content_payloads(tmp_path: Path) -> None:
    """Files under content/ are payload bodies, not nodes."""
    vault = _make_vault(tmp_path / "v", count=3)
    assert _count_nodes(vault) == (3, 3)


def test_count_ignores_appledouble_companions(tmp_path: Path) -> None:
    """macOS tar writes ``._name`` beside every file; they are not nodes.

    Regression: these extract as real files ending in ``.md``, so a vault
    tarred on macOS reported double its node count and, worse, dropped binary
    resource-fork data into the vault for the graph compiler to choke on.
    """
    vault = _make_vault(tmp_path / "v", count=3)
    (vault / "._node-0.md").write_bytes(b"\x00\x05\x16\x07AppleDouble")
    (vault / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    assert _count_nodes(vault) == (3, 3)


# ── install ─────────────────────────────────────────────────────────────


def test_install_from_directory(tmp_path: Path) -> None:
    src = _make_vault(tmp_path / "src", count=4)
    dest = tmp_path / "vault" / "nodes"
    assert _run(["vault", "install", str(src), "--dest", str(dest)]) == 0
    assert _count_nodes(dest) == (4, 4)
    # content_ref payloads travel with the nodes that address them.
    assert (dest / "content" / "skill" / "REFERENCE.md").is_file()


def test_install_leaves_repository_furniture_behind(tmp_path: Path) -> None:
    """A vault distributed as a git repo carries files that are not nodes.

    This is not tidiness. The graph compiler treats any markdown in the vault
    without ``akms_schema`` as a schema error and re-raises it regardless of
    strictness, so a README copied into the vault makes every later build fail.
    Every GitHub repository has one.
    """
    src = _make_vault(tmp_path / "src", count=3)
    (src / "README.md").write_text(
        "# Vault\n\nProse, no frontmatter.\n", encoding="utf-8"
    )
    (src / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (src / ".github" / "workflows").mkdir(parents=True)
    (src / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\n", encoding="utf-8"
    )

    dest = tmp_path / "vault" / "nodes"
    assert _run(["vault", "install", str(src), "--dest", str(dest)]) == 0
    assert _count_nodes(dest) == (3, 3)
    assert not (dest / "README.md").exists()
    assert not (dest / "LICENSE").exists()
    assert not (dest / ".github").exists()


def test_a_readme_documenting_the_node_format_is_not_a_node(tmp_path: Path) -> None:
    """A vault's README explains the format, so it *mentions* ``akms_schema``.

    Regression: a substring test classified such a README as a node, installed
    it, and the graph compiler then aborted every build on it. The real vault
    README hit this immediately. Detection has to be structural — frontmatter
    fence first, key at the top level of that block.
    """
    src = _make_vault(tmp_path / "src", count=3)
    (src / "README.md").write_text(
        "# My Vault\n\n"
        "Every node declares `akms_schema` in its frontmatter:\n\n"
        "```yaml\n"
        "---\n"
        "akms_schema: v2\n"
        "id: example\n"
        "---\n"
        "```\n",
        encoding="utf-8",
    )
    dest = tmp_path / "vault" / "nodes"
    assert _run(["vault", "install", str(src), "--dest", str(dest)]) == 0
    assert _count_nodes(dest) == (3, 3)
    assert not (dest / "README.md").exists()


def test_install_reports_what_it_left_behind(tmp_path: Path, capsys) -> None:
    src = _make_vault(tmp_path / "src", count=2)
    (src / "README.md").write_text("# Vault\n", encoding="utf-8")
    dest = tmp_path / "vault" / "nodes"
    assert _run(["vault", "install", str(src), "--dest", str(dest), "--json"]) == 0
    assert '"README.md"' in capsys.readouterr().out


def test_install_refuses_to_replace_a_populated_vault(tmp_path: Path) -> None:
    src = _make_vault(tmp_path / "src", count=2)
    dest = _make_vault(tmp_path / "existing", count=5)
    assert _run(["vault", "install", str(src), "--dest", str(dest)]) == 1
    # Untouched.
    assert _count_nodes(dest) == (5, 5)


def test_force_replaces_rather_than_merges(tmp_path: Path) -> None:
    src = _make_vault(tmp_path / "src", count=2)
    dest = _make_vault(tmp_path / "existing", count=5)
    assert _run(["vault", "install", str(src), "--dest", str(dest), "--force"]) == 0
    assert _count_nodes(dest) == (2, 2)


def test_install_without_a_source_is_a_usage_error(tmp_path: Path) -> None:
    assert _run(["vault", "install", "--dest", str(tmp_path / "v")]) == 2


def test_install_rejects_a_directory_holding_no_nodes(tmp_path: Path) -> None:
    src = tmp_path / "notavault"
    src.mkdir()
    (src / "README.md").write_text("no frontmatter here\n", encoding="utf-8")
    assert _run(["vault", "install", str(src), "--dest", str(tmp_path / "v")]) == 1
    assert not (tmp_path / "v").exists()


def test_install_rejects_plain_http(tmp_path: Path) -> None:
    assert (
        _run(
            [
                "vault",
                "install",
                "http://example.invalid/vault.tar.gz",
                "--dest",
                str(tmp_path / "v"),
            ]
        )
        == 1
    )


def test_install_from_tarball_strips_junk(tmp_path: Path) -> None:
    src = _make_vault(tmp_path / "src", count=3)
    (src / "._node-0.md").write_bytes(b"\x00\x05\x16\x07AppleDouble")
    archive = tmp_path / "vault.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname="vault-v1.0.0")

    dest = tmp_path / "vault" / "nodes"
    assert _run(["vault", "install", str(archive), "--dest", str(dest)]) == 0
    assert _count_nodes(dest) == (3, 3)
    assert not (dest / "._node-0.md").exists()


def test_install_refuses_an_archive_that_escapes_the_destination(
    tmp_path: Path,
) -> None:
    """Path traversal in a downloaded archive must not write outside the vault."""
    outside = tmp_path / "outside.md"
    src = _make_vault(tmp_path / "src", count=1)
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src / "node-0.md", arcname="vault/node-0.md")
        info = tarfile.TarInfo(name="vault/../../escaped.md")
        payload = b"akms_schema: v2\n"
        info.size = len(payload)
        import io

        tar.addfile(info, io.BytesIO(payload))

    dest = tmp_path / "vault" / "nodes"
    assert _run(["vault", "install", str(archive), "--dest", str(dest)]) == 1
    assert not outside.exists()
    assert not (tmp_path / "escaped.md").exists()


# ── status ──────────────────────────────────────────────────────────────


def test_status_reports_a_missing_vault(tmp_path: Path, capsys) -> None:
    assert _run(["vault", "status", "--vault", str(tmp_path / "nope")]) == 0
    out = capsys.readouterr().out
    assert "not present" in out
    assert "akms vault install" in out


def test_status_counts_an_installed_vault(tmp_path: Path, capsys) -> None:
    vault = _make_vault(tmp_path / "v", count=7)
    assert _run(["vault", "status", "--vault", str(vault), "--json"]) == 0
    assert '"markdown_files": 7' in capsys.readouterr().out
