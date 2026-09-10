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

# Set this once the canonical vault publishes its first tagged release; until
# then a source must be given explicitly rather than guessed at.
DEFAULT_VAULT_SOURCE: str | None = None


class VaultInstallError(RuntimeError):
    """Raised when a vault cannot be fetched, validated, or installed."""


def _count_nodes(directory: Path) -> tuple[int, int]:
    """Return (markdown files, files that declare ``akms_schema``).

    Deliberately cheap and tolerant: this is a sanity check on a downloaded
    archive, not schema validation. The graph compiler does the real parsing
    and reports precisely what it rejects.
    """
    md = 0
    schema = 0
    for path in directory.rglob("*.md"):
        if path.name.startswith("."):
            continue
        if "content" in path.relative_to(directory).parts[:-1]:
            continue
        md += 1
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:2048]
        except OSError:
            continue
        if "akms_schema" in head:
            schema += 1
    return md, schema


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


def _fetch(source: str, workdir: Path) -> Path:
    """Resolve ``source`` to a directory of vault content inside ``workdir``."""
    staged = workdir / "staged"

    if source.startswith(("http://", "https://")):
        if source.startswith("http://"):
            raise VaultInstallError(
                "refusing to fetch a vault over plain http; use https"
            )
        import urllib.request

        archive = workdir / "vault.tar.gz"
        try:
            with urllib.request.urlopen(source) as response:  # noqa: S310 - https enforced
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
        print("      akms vault install <url-or-path>")
        return 0
    print(f"  status: {md} node file(s), {schema} declaring akms_schema")
    if md == 0:
        print()
        print("  The vault is empty. Install one with:")
        print("      akms vault install <url-or-path>")
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

    try:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            content = _fetch(source, workdir)

            md, schema = _count_nodes(content)
            if md == 0:
                raise VaultInstallError(
                    f"{source!r} contains no node markdown files; refusing to "
                    "install it as a vault"
                )
            if schema == 0:
                raise VaultInstallError(
                    f"{source!r} has {md} markdown file(s) but none declare "
                    "`akms_schema`; this does not look like an AKMS vault"
                )

            # Stage beside the destination and swap, so an interrupted install
            # cannot leave a half-written vault where a working one used to be.
            dest.parent.mkdir(parents=True, exist_ok=True)
            incoming = dest.parent / f".{dest.name}.incoming"
            if incoming.exists():
                shutil.rmtree(incoming)
            # macOS `tar` writes AppleDouble `._name` companions beside every
            # file, and they extract as real files ending in `.md`. Left in,
            # they land in the vault and the graph compiler tries to parse
            # binary resource-fork data as v2 nodes. Same reasoning for
            # `.DS_Store`, which had already reached the published wheel once.
            shutil.copytree(
                content,
                incoming,
                ignore=shutil.ignore_patterns("._*", ".DS_Store", "__pycache__"),
            )

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

    result = {"vault": str(dest), "source": source, "nodes": md}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Installed {md} node file(s) into {dest}")
        print(f"  source: {source}")
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
        help="Directory, .tar.gz, or https URL holding the vault",
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
