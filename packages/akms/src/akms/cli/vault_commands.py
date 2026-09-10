"""CLI commands for inspecting and installing a global node vault.

The node corpus is not shipped inside the ``akms`` wheel. It never was
reachable from one: ``resolve_global_vault`` picks an explicit argument, then
``AKMS_GLOBAL_VAULT``, then ``global_vault`` from the propagation config, then
``~/.claude/akms/nodes`` — the package directory is on none of those paths. A
corpus bundled into the package could only ever be dead weight, so vaults are
distributed on their own and installed here, deliberately, by the user.

That "by the user" is the whole design. Nothing in AKMS writes to the global
vault on its own; ``vault install`` is a foreground command that says what it
is about to do and refuses to overwrite an existing vault without ``--force``.

Registered via :func:`register_vault_commands`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

# The canonical vault, pinned to a tag rather than a branch: `vault install`
# with no argument should install the same content today and in a year, and a
# moving `main` would make it silently install something else. Bump this when
# a new vault release is cut.
DEFAULT_VAULT_SOURCE: str | None = (
    "https://github.com/CEmM2/akms-vault-compmech/archive/refs/tags/v1.0.0.tar.gz"
)


class VaultInstallError(RuntimeError):
    """Raised when a vault cannot be fetched, validated, or installed."""


def _declares_schema(path: Path) -> bool:
    """Does this file open with frontmatter declaring ``akms_schema``?

    Deliberately structural rather than a substring search. A vault's own
    README documents the node format, so it contains the text ``akms_schema``
    in a fenced example — and a plain ``"akms_schema" in text`` test classifies
    that README as a node, installs it into the vault, and the graph compiler
    then aborts every build on it. Found exactly that way.

    So: the file must *start* with a frontmatter fence, and the key must appear
    at the top level of that block, before it closes.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    lines = text.splitlines()
    for line in lines[1:]:
        if line.rstrip() in {"---", "..."}:
            return False
        if line.startswith("akms_schema:"):
            return True
    return False


def _count_nodes(directory: Path) -> tuple[int, int]:
    """Return (markdown files, files that declare ``akms_schema``).

    A sanity check on a source tree, not schema validation. The graph compiler
    does the real parsing and reports precisely what it rejects.
    """
    md = 0
    schema = 0
    for path in directory.rglob("*.md"):
        if path.name.startswith("."):
            continue
        if "content" in path.relative_to(directory).parts[:-1]:
            continue
        md += 1
        if _declares_schema(path):
            schema += 1
    return md, schema


def _is_node(path: Path) -> bool:
    """Does this file look like a v2 node rather than repository furniture?"""
    if path.suffix != ".md" or path.name.startswith("."):
        return False
    return _declares_schema(path)


def _install_tree(src: Path, dest: Path) -> tuple[int, list[str]]:
    """Copy vault content from ``src`` to ``dest``, leaving furniture behind.

    A vault distributed as a git repository carries a README, a licence, CI
    configuration — and the graph compiler treats *any* markdown in the vault
    that lacks ``akms_schema`` as a schema error and re-raises it regardless of
    strictness. So installing a repository wholesale makes every subsequent
    build fail on its own README. Rather than push that onto vault authors as a
    layout rule to remember, the installer copies only what a vault is: nodes
    that declare ``akms_schema``, and the ``content/`` payload tree they
    address through ``content_ref``.

    Returns the node count and the top-level names that were left behind, so
    the caller can say what it skipped instead of silently discarding things.
    """
    nodes = 0
    skipped: set[str] = set()
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if "content" in rel.parts[:-1]:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            continue
        if _is_node(path):
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            nodes += 1
        else:
            skipped.add(rel.parts[0])
    return nodes, sorted(skipped)


def _safe_extract(archive: Path, dest: Path) -> None:
    """Extract a tar archive, refusing members that escape ``dest``.

    Uses the stdlib ``data`` filter where available (3.12, and 3.11.4+), which
    rejects absolute paths, parent traversal, links pointing outside the tree,
    device nodes and setuid bits. The explicit check below is not redundant:
    it keeps the guarantee on interpreters whose tarfile predates the filter,
    and it states the invariant at the call site rather than trusting a
    default that has changed across versions.
    """
    dest_resolved = dest.resolve()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            target = (dest_resolved / member.name).resolve()
            if not target.is_relative_to(dest_resolved):
                raise VaultInstallError(
                    f"archive member {member.name!r} escapes the destination "
                    "directory; refusing to extract"
                )
            if member.issym() or member.islnk():
                link = (target.parent / member.linkname).resolve()
                if not link.is_relative_to(dest_resolved):
                    raise VaultInstallError(
                        f"archive member {member.name!r} links outside the "
                        "destination directory; refusing to extract"
                    )
        try:
            tar.extractall(dest_resolved, filter="data")
        except TypeError:  # tarfile without the filter argument
            tar.extractall(dest_resolved)  # noqa: S202 - members checked above


def _https_only_redirect_handler():
    """A redirect handler that follows redirects but never off https.

    ``urlopen`` follows redirects by itself, so checking only the URL the user
    typed would let an https source hand off to plain http mid-flight and still
    be treated as trusted. Redirects cannot simply be refused either: GitHub's
    archive URLs redirect to codeload, which is the normal path for
    ``akms vault install <release tarball>``. So follow them — refuse only the
    downgrade.

    Built lazily so importing this module does not pull in urllib.
    """
    import urllib.request

    class _HTTPSOnlyRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not newurl.lower().startswith("https://"):
                scheme = newurl.split(":", 1)[0]
                raise VaultInstallError(
                    f"refusing a redirect from https to {scheme}: {newurl}"
                )
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return _HTTPSOnlyRedirects


def _fetch(source: str, workdir: Path) -> Path:
    """Resolve ``source`` to a directory of vault content inside ``workdir``."""
    staged = workdir / "staged"

    if source.startswith(("http://", "https://")):
        if source.startswith("http://"):
            raise VaultInstallError(
                "refusing to fetch a vault over plain http; use https"
            )
        import urllib.request

        opener = urllib.request.build_opener(_https_only_redirect_handler())
        archive = workdir / "vault.tar.gz"
        try:
            with opener.open(source) as response:  # noqa: S310 - https enforced above
                archive.write_bytes(response.read())
        except OSError as exc:
            raise VaultInstallError(f"could not download {source}: {exc}") from exc
        staged.mkdir()
        _safe_extract(archive, staged)
        return _descend_single_root(staged)

    local = Path(source).expanduser()
    if local.is_dir():
        return local
    if local.is_file() and "".join(local.suffixes[-2:]) in {".tar.gz", ".tgz"}:
        staged.mkdir()
        _safe_extract(local, staged)
        return _descend_single_root(staged)
    raise VaultInstallError(
        f"{source!r} is not a directory, a .tar.gz, or an https URL"
    )


def _descend_single_root(staged: Path) -> Path:
    """A GitHub tarball wraps everything in one ``repo-tag/`` directory."""
    entries = [p for p in staged.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return staged


def cmd_vault_status(args: argparse.Namespace) -> int:
    """Report where the vault resolves and what is in it."""
    from akms.graph.build_graph import resolve_global_vault

    vault = resolve_global_vault(explicit=args.vault)
    exists = vault.is_dir()
    md, schema = _count_nodes(vault) if exists else (0, 0)

    info: dict[str, Any] = {
        "vault": str(vault),
        "exists": exists,
        "markdown_files": md,
        "nodes_declaring_akms_schema": schema,
    }
    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0

    print("AKMS global vault")
    print(f"  path: {vault}")
    if not exists:
        print("  status: not present")
        print()
        print("  No vault is installed. Install one with:")
        print("      akms vault install")
        return 0
    print(f"  status: {md} node file(s), {schema} declaring akms_schema")
    if md == 0:
        print()
        print("  The vault is empty. Install one with:")
        print("      akms vault install")
    return 0


def cmd_vault_install(args: argparse.Namespace) -> int:
    """Install a vault into the resolved global vault directory."""
    from akms.graph.build_graph import resolve_global_vault

    source = args.source or DEFAULT_VAULT_SOURCE
    if not source:
        print(
            "error: no vault source given.\n"
            "\n"
            "Pass a source explicitly — a directory, a .tar.gz, or an https\n"
            "URL to a released vault archive:\n"
            "\n"
            "    akms vault install ./my-vault\n"
            "    akms vault install https://example.org/vault-v1.0.0.tar.gz\n",
            file=sys.stderr,
        )
        return 2

    dest = Path(args.dest).expanduser() if args.dest else resolve_global_vault()

    if dest.is_dir():
        existing_md, _ = _count_nodes(dest)
        if existing_md and not args.force:
            print(
                f"error: {dest} already holds {existing_md} node file(s).\n"
                "\n"
                "Automated AKMS operations treat the global vault as read-only,\n"
                "so this command will not replace one you already have. Re-run\n"
                "with --force to replace it, or --dest to install elsewhere.",
                file=sys.stderr,
            )
            return 1

    md = 0
    skipped: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            content = _fetch(source, workdir)

            _total, schema = _count_nodes(content)
            if _total == 0:
                raise VaultInstallError(
                    f"{source!r} contains no node markdown files; refusing to "
                    "install it as a vault"
                )
            if schema == 0:
                raise VaultInstallError(
                    f"{source!r} has {_total} markdown file(s) but none declare "
                    "`akms_schema`; this does not look like an AKMS vault"
                )

            # Stage beside the destination and swap, so an interrupted install
            # cannot leave a half-written vault where a working one used to be.
            dest.parent.mkdir(parents=True, exist_ok=True)
            incoming = dest.parent / f".{dest.name}.incoming"
            if incoming.exists():
                shutil.rmtree(incoming)
            incoming.mkdir(parents=True)
            # Copies nodes and content/ payloads only. Dotfiles are excluded by
            # the same pass, which also drops the AppleDouble `._name`
            # companions macOS `tar` writes beside every file — they extract as
            # real files ending in `.md`, and the compiler would try to parse
            # resource-fork binary as a v2 node.
            md, skipped = _install_tree(content, incoming)

            previous = dest.parent / f".{dest.name}.previous"
            if dest.exists():
                if previous.exists():
                    shutil.rmtree(previous)
                dest.rename(previous)
            incoming.rename(dest)
            if previous.exists():
                shutil.rmtree(previous)
    except VaultInstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    result = {
        "vault": str(dest),
        "source": source,
        "nodes": md,
        "skipped": skipped,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Installed {md} node file(s) into {dest}")
        print(f"  source: {source}")
        if skipped:
            print(f"  not vault content, left behind: {', '.join(skipped)}")
        print()
        print("Verify with:  akms vault status")
    return 0


def register_vault_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``vault`` command group on the root parser."""
    vault = subparsers.add_parser(
        "vault",
        help="Inspect or install the global node vault",
        description=(
            "The node corpus is distributed separately from the akms package. "
            "These commands report where AKMS looks for it and install one."
        ),
    )
    vault_sub = vault.add_subparsers(dest="vault_command")

    status = vault_sub.add_parser(
        "status",
        help="Show where the global vault resolves and what it holds",
    )
    status.add_argument(
        "--vault",
        help="Inspect this path instead of the resolved global vault",
    )
    status.add_argument("--json", action="store_true", help="Emit JSON")
    status.set_defaults(func=cmd_vault_status)

    install = vault_sub.add_parser(
        "install",
        help="Install a vault into the global vault directory",
        description=(
            "Accepts a local directory, a local .tar.gz, or an https URL to a "
            "released vault archive. Refuses to replace a vault that already "
            "holds nodes unless --force is given."
        ),
    )
    install.add_argument(
        "source",
        nargs="?",
        help=(
            "Directory, .tar.gz, or https URL holding the vault. "
            "Defaults to the canonical vault release."
        ),
    )
    install.add_argument(
        "--dest",
        help="Install here instead of the resolved global vault",
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing non-empty vault",
    )
    install.add_argument("--json", action="store_true", help="Emit JSON")
    install.set_defaults(func=cmd_vault_install)

    def _require_subcommand(args: argparse.Namespace) -> int:
        vault.print_help()
        return 2

    vault.set_defaults(func=_require_subcommand)
