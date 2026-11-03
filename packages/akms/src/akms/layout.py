"""Where a repository keeps its local AKMS knowledge."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

# New projects store lessons, the graph, and generated outputs here.
DEFAULT_KNOWLEDGE_DIRNAME = ".knowledge"
# Checkouts that already use the older directory keep it.
LEGACY_KNOWLEDGE_DIRNAME = "knowledge"


def local_knowledge_dir(repo_root: str | Path) -> Path:
    """Return the local knowledge directory for ``repo_root``.

    The default is ``<repo>/.knowledge``. A repository that already has
    ``<repo>/knowledge`` and does not yet have ``.knowledge`` keeps that
    older directory, so existing checkouts resolve unchanged.
    """
    root = Path(repo_root)
    dotted = root / DEFAULT_KNOWLEDGE_DIRNAME
    legacy = root / LEGACY_KNOWLEDGE_DIRNAME
    if dotted.is_dir():
        return dotted
    if legacy.is_dir():
        return legacy
    return dotted


# ═══════════════════════════════════════════════════════════════════════
#  Moving a repository from knowledge/ to .knowledge/
# ═══════════════════════════════════════════════════════════════════════


class KnowledgeLayoutError(Exception):
    """A layout migration that cannot run, with a stable ``code``."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LineEdit:
    """One rewritten line of a git ignore or attributes file."""

    file: str
    line: int
    before: str
    after: str


@dataclass(frozen=True)
class Mention:
    """A tracked line that still names the old directory; reported, not changed."""

    file: str
    line: int
    text: str


@dataclass
class KnowledgeMigration:
    """What a knowledge-directory migration does, or did."""

    repo_root: Path
    status: str
    move: str = "none"
    edits: list[LineEdit] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "repo_root": str(self.repo_root),
            "from": LEGACY_KNOWLEDGE_DIRNAME,
            "to": DEFAULT_KNOWLEDGE_DIRNAME,
            "move": self.move,
            "edits": [asdict(edit) for edit in self.edits],
            "removed": list(self.removed),
            "mentions": [asdict(mention) for mention in self.mentions],
        }


# Compiled outputs that hold paths of the old directory. The next reader
# recompiles them, as after a node status change.
_COMPILED = ("graph/graph.json",)
_QMD_CACHE = "graph/.qmd_cache"
_IGNORE_FILES = (".gitignore", ".gitattributes")
# Text such as `knowledge/`, `dev/knowledge/` or `/knowledge/`, but not
# `.knowledge/` or `my_knowledge/`.
_MENTION = re.compile(rf"(?<![\w.-]){LEGACY_KNOWLEDGE_DIRNAME}/")
_MAX_SCAN_BYTES = 1_000_000


def ignored_legacy_dir(repo_root: str | Path) -> Path | None:
    """The ``knowledge/`` directory that ``.knowledge/`` is hiding, if any.

    When both exist, every AKMS reader uses ``.knowledge/`` and nothing in
    ``knowledge/`` is loaded.
    """
    root = Path(repo_root)
    dotted = root / DEFAULT_KNOWLEDGE_DIRNAME
    legacy = root / LEGACY_KNOWLEDGE_DIRNAME
    if dotted.is_dir() and legacy.is_dir() and any(legacy.iterdir()):
        return legacy
    return None


def plan_knowledge_migration(repo_root: str | Path) -> KnowledgeMigration:
    """Describe moving ``<repo>/knowledge/`` to ``<repo>/.knowledge/``; change nothing.

    Raises :class:`KnowledgeLayoutError` when the move cannot be done safely.
    """
    root = Path(repo_root).resolve(strict=True)
    legacy = root / LEGACY_KNOWLEDGE_DIRNAME
    dotted = root / DEFAULT_KNOWLEDGE_DIRNAME
    if legacy.is_symlink():
        raise KnowledgeLayoutError(
            f"{legacy} is a symbolic link; move it by hand", code="symlink"
        )
    if not legacy.is_dir():
        if dotted.is_dir():
            return KnowledgeMigration(repo_root=root, status="already_migrated")
        raise KnowledgeLayoutError(
            f"No {LEGACY_KNOWLEDGE_DIRNAME}/ directory under {root}",
            code="no_legacy_dir",
        )
    if dotted.is_symlink() or (dotted.exists() and not dotted.is_dir()):
        raise KnowledgeLayoutError(
            f"{dotted} exists and is not a directory", code="target_exists"
        )
    if dotted.is_dir() and any(dotted.iterdir()):
        raise KnowledgeLayoutError(
            f"Both {LEGACY_KNOWLEDGE_DIRNAME}/ and {DEFAULT_KNOWLEDGE_DIRNAME}/ "
            f"exist under {root}. AKMS reads only {DEFAULT_KNOWLEDGE_DIRNAME}/, so "
            f"{LEGACY_KNOWLEDGE_DIRNAME}/ is ignored; merge them by hand",
            code="both_present",
        )

    top = _git_toplevel(root)
    tracked = top is not None and bool(_git(root, "ls-files", "-z", "--", legacy.name))
    plan = KnowledgeMigration(
        repo_root=root, status="planned", move="git-mv" if tracked else "rename"
    )
    ignore_files = [root / name for name in _IGNORE_FILES]
    if top is not None and top != root:
        ignore_files += [top / name for name in _IGNORE_FILES]
    for path in ignore_files:
        plan.edits.extend(_ignore_edits(path, legacy, display_root=top or root))
    for relative in (*_COMPILED, _QMD_CACHE):
        if (legacy / relative).exists():
            plan.removed.append(f"{DEFAULT_KNOWLEDGE_DIRNAME}/{relative}")
    if top is not None:
        edited = {(edit.file, edit.line) for edit in plan.edits}
        plan.mentions = _mentions(top, legacy, skip=edited)
    return plan


def migrate_knowledge_layout(
    repo_root: str | Path, *, check: bool = False
) -> KnowledgeMigration:
    """Move ``<repo>/knowledge/`` to ``<repo>/.knowledge/``.

    Tracked directories move with ``git mv`` so history follows them. Lines of
    ``.gitignore`` and ``.gitattributes`` anchored on the old directory are
    rewritten, and the compiled graph and qmd cache are removed so the next
    reader recompiles. Other mentions of ``knowledge/`` are only reported.
    ``check`` returns the plan and changes nothing. A failure part-way
    restores the directory and the edited files.
    """
    plan = plan_knowledge_migration(repo_root)
    if check or plan.status != "planned":
        return plan
    root = plan.repo_root
    legacy = root / LEGACY_KNOWLEDGE_DIRNAME
    dotted = root / DEFAULT_KNOWLEDGE_DIRNAME
    originals: dict[Path, bytes] = {}
    moved = False
    try:
        if dotted.is_dir():
            dotted.rmdir()  # empty, checked by the plan
        if plan.move == "git-mv":
            _git(root, "mv", legacy.name, dotted.name)
        else:
            legacy.rename(dotted)
        moved = True
        display_root = _git_toplevel(root) or root
        for path in {display_root / edit.file for edit in plan.edits}:
            originals[path] = path.read_bytes()
            path.write_bytes(_apply_edits(originals[path], path, plan, display_root))
        for relative in _COMPILED:
            (dotted / relative).unlink(missing_ok=True)
        cache = dotted / _QMD_CACHE
        for entry in cache.glob("*.json") if cache.is_dir() else ():
            entry.unlink()
    except Exception:
        for path, content in originals.items():
            path.write_bytes(content)
        if moved:
            if plan.move == "git-mv":
                _git(root, "mv", dotted.name, legacy.name)
            else:
                dotted.rename(legacy)
        raise
    plan.status = "migrated"
    return plan


def _git(cwd: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise KnowledgeLayoutError(
            f"git {' '.join(arguments[:2])} failed: {detail}", code="git"
        )
    return completed.stdout


def _git_toplevel(root: Path) -> Path | None:
    try:
        return Path(_git(root, "rev-parse", "--show-toplevel").decode().strip())
    except (KnowledgeLayoutError, OSError, subprocess.SubprocessError):
        return None


def _rewrite_pattern(pattern: str, old: str, new: str) -> str | None:
    """``pattern`` re-anchored on the new directory, or None if it is not anchored on ``old``."""
    negation = "!" if pattern.startswith("!") else ""
    body = pattern[len(negation) :]
    slash = "/" if body.startswith("/") else ""
    rest = body[len(slash) :]
    if rest == old or rest.startswith(f"{old}/"):
        return f"{negation}{slash}{new}{rest[len(old) :]}"
    return None


def _ignore_edits(path: Path, legacy: Path, *, display_root: Path) -> list[LineEdit]:
    if not path.is_file():
        return []
    old = Path(os.path.relpath(legacy, path.parent)).as_posix()
    if old.startswith(".."):
        return []
    new = (PurePosixPath(old).parent / DEFAULT_KNOWLEDGE_DIRNAME).as_posix()
    edits: list[LineEdit] = []
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pattern = stripped.split()[0]
        rewritten = _rewrite_pattern(pattern, old, new)
        if rewritten is None:
            continue
        after = line.replace(pattern, rewritten, 1)
        edits.append(
            LineEdit(
                file=path.relative_to(display_root).as_posix(),
                line=number,
                before=line,
                after=after,
            )
        )
    return edits


def _apply_edits(
    content: bytes, path: Path, plan: KnowledgeMigration, display_root: Path
) -> bytes:
    lines = content.decode("utf-8", errors="surrogateescape").splitlines(keepends=True)
    for edit in plan.edits:
        if display_root / edit.file != path:
            continue
        line = lines[edit.line - 1]
        ending = line[len(line.rstrip("\r\n")) :]
        lines[edit.line - 1] = edit.after + ending
    return "".join(lines).encode("utf-8", errors="surrogateescape")


def _mentions(top: Path, legacy: Path, *, skip: set[tuple[str, int]]) -> list[Mention]:
    moved = legacy.relative_to(top).as_posix() if legacy != top else ""
    mentions: list[Mention] = []
    for raw in _git(top, "ls-files", "-z").split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="replace")
        if moved and (relative == moved or relative.startswith(f"{moved}/")):
            continue
        path = top / relative
        try:
            if path.is_symlink() or path.stat().st_size > _MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if (relative, number) not in skip and _MENTION.search(line):
                mentions.append(Mention(relative, number, line.strip()[:200]))
    return mentions
