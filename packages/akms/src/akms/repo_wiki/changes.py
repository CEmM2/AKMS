"""Map a git diff to the symbols it touches, and those symbols to their direct callers.

Line ranges come from parsing each changed file with the same extractors ``build`` uses:
the new side from the worktree (or the index, for ``--staged``), the old side from the base
revision, so deleted symbols keep their old ranges. The symbol graph is then overlaid with
the new side of every changed file, so callers reflect the tree being committed whether the
graph was built before or after the edits.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from akms.repo_wiki.code_graph import (
    CONFIDENT,
    HEURISTIC,
    CodeGraph,
    Edge,
    is_test_path,
    load_code_graph,
)
from akms.repo_wiki.errors import RepoWikiError
from akms.repo_wiki.hashing import sha256_bytes
from akms.repo_wiki.impact import RISK_LEVELS, Hit, assess_risk, node_summary
from akms.repo_wiki.models import ParsedModule, SourceFile, Symbol
from akms.repo_wiki.scanner import (
    LANGUAGE_BY_SUFFIX,
    _enabled_language_globs,
    matches_any,
)

CHANGES_SCHEMA = "repo-wiki/changes/v1"

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_STATUS = {"A": "added", "C": "added", "D": "deleted", "R": "renamed"}


class GitError(RepoWikiError):
    """A git invocation failed or the repository is not a git work tree."""


@dataclass(slots=True)
class Hunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int

    def to_dict(self) -> dict[str, int]:
        return {
            "old_start": self.old_start,
            "old_lines": self.old_lines,
            "new_start": self.new_start,
            "new_lines": self.new_lines,
        }


@dataclass(slots=True)
class FileChange:
    path: str
    old_path: str | None
    status: str  # added | modified | deleted | renamed
    hunks: list[Hunk] = field(default_factory=list)
    binary: bool = False


# ------------------------------------------------------------------------- git


def _git(repo_root: Path, *args: str, check: bool = True) -> bytes:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(repo_root), "-c", "core.quotepath=false", *args],
        check=False,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or b"").decode(
            "utf-8", errors="replace"
        )
        raise GitError(f"git {' '.join(args[:2])} failed: {detail.strip()}")
    return completed.stdout if completed.returncode == 0 else b""


def _rev(repo_root: Path, ref: str) -> str | None:
    if not ref or ref.startswith("-"):
        raise GitError(f"invalid git ref: {ref!r}")
    out = _git(
        repo_root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False
    )
    return out.decode().strip() or None


def _unquote(path: str) -> str:
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        raw = path[1:-1].encode("latin-1", errors="backslashreplace")
        return raw.decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")
    return path


def _strip_prefix(path: str) -> str | None:
    path = _unquote(path.rstrip("\t"))
    if path == "/dev/null":
        return None
    return path[2:] if path[:2] in ("a/", "b/") else path


def parse_name_status(raw: bytes) -> list[FileChange]:
    """Parse ``git diff --name-status -z -M`` output."""
    tokens = [t.decode("utf-8", errors="replace") for t in raw.split(b"\0")]
    changes: list[FileChange] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if not status:
            continue
        letter = status[0]
        if letter in ("R", "C"):
            old, new = tokens[index], tokens[index + 1]
            index += 2
            if letter == "R":
                changes.append(FileChange(new, old, "renamed"))
            else:
                changes.append(FileChange(new, None, "added"))
        else:
            path = tokens[index]
            index += 1
            changes.append(FileChange(path, path, _STATUS.get(letter, "modified")))
    for change in changes:
        if change.status == "added":
            change.old_path = None
    return changes


def parse_unified_hunks(text: str) -> dict[str, tuple[list[Hunk], bool]]:
    """Parse ``git diff -U0`` into ``{path: (hunks, binary)}`` keyed by new (else old) path."""
    result: dict[str, tuple[list[Hunk], bool]] = {}
    old: str | None = None
    new: str | None = None
    hunks: list[Hunk] = []
    binary = False
    in_header = False

    def flush() -> None:
        key = new or old
        if key:
            result[key] = (hunks, binary)

    for line in text.splitlines():
        if line.startswith("diff --git "):
            flush()
            old = new = None
            hunks = []
            binary = False
            in_header = True
            continue
        if in_header:
            if line.startswith("--- "):
                old = _strip_prefix(line[4:])
                continue
            if line.startswith("+++ "):
                new = _strip_prefix(line[4:])
                continue
            if line.startswith("rename from "):
                old = _unquote(line[len("rename from ") :])
                continue
            if line.startswith("rename to "):
                new = _unquote(line[len("rename to ") :])
                continue
            if line.startswith("Binary files "):
                binary = True
                continue
        match = _HUNK.match(line)
        if match:
            in_header = False
            old_start, old_len, new_start, new_len = match.groups()
            hunks.append(
                Hunk(
                    int(old_start),
                    1 if old_len is None else int(old_len),
                    int(new_start),
                    1 if new_len is None else int(new_len),
                )
            )
    flush()
    return result


# ------------------------------------------------------------------ extraction


def _extractable(rel: str, config: dict[str, object]) -> str | None:
    """The language *rel* would be parsed as by ``build``, or ``None``."""
    from akms.repo_wiki.extract.registry import get_backend

    language = LANGUAGE_BY_SUFFIX.get(PurePosixPath(rel).suffix.lower())
    if language is None or get_backend(language, config) is None:
        return None
    scanner = config.get("scanner")
    include: list[str] = []
    if isinstance(scanner, dict):
        include = [str(v) for v in scanner.get("include", [])]
    if include and not matches_any(rel, include + _enabled_language_globs(config)):
        return None
    return language


def _extract(source: SourceFile, config: dict[str, object]) -> ParsedModule | None:
    from akms.repo_wiki.extract.registry import extract_files

    return extract_files([source], config).parsed_modules.get(source.path)


def extract_path(
    repo_root: Path, rel: str, config: dict[str, object]
) -> ParsedModule | None:
    """Parse one repository file as ``build`` would (``None`` if it has no extractor)."""
    language = _extractable(rel, config)
    path = repo_root / rel
    if language is None or not path.is_file():
        return None
    data = path.read_bytes()
    return _extract(
        SourceFile(rel, str(path), language, len(data), sha256_bytes(data)), config
    )


def extract_text(
    rel: str, data: bytes, config: dict[str, object]
) -> ParsedModule | None:
    """Parse *data* as if it were the repository file *rel* (IDs match the real file)."""
    language = _extractable(rel, config)
    if language is None:
        return None
    with tempfile.TemporaryDirectory(prefix="repo-wiki-changes-") as tmp:
        path = Path(tmp) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return _extract(
            SourceFile(rel, str(path), language, len(data), sha256_bytes(data)), config
        )


# --------------------------------------------------------------------- mapping


def _effective_ranges(symbols: list[Symbol], text: str) -> dict[str, tuple[int, int]]:
    """Symbol line ranges, extended upward over Python decorator lines."""
    lines = text.splitlines()
    ranges: dict[str, tuple[int, int]] = {}
    for symbol in symbols:
        start = symbol.start_line
        if symbol.path.endswith((".py", ".pyi")):
            while start > 1 and lines[start - 2].lstrip().startswith("@"):
                start -= 1
        ranges[symbol.symbol_id] = (start, symbol.end_line)
    return ranges


def _innermost(
    symbols: list[Symbol], ranges: dict[str, tuple[int, int]], lines: set[int]
) -> tuple[set[str], list[int]]:
    """Innermost symbol per changed line, plus the lines outside every symbol."""
    touched: set[str] = set()
    outside: list[int] = []
    spans = sorted(
        (
            (ranges[s.symbol_id][1] - ranges[s.symbol_id][0], s.symbol_id)
            for s in symbols
        )
    )
    for line in sorted(lines):
        for _, symbol_id in spans:
            start, end = ranges[symbol_id]
            if start <= line <= end:
                touched.add(symbol_id)
                break
        else:
            outside.append(line)
    return touched, outside


def _line_set(hunks: list[Hunk], *, new_side: bool) -> set[int]:
    lines: set[int] = set()
    for hunk in hunks:
        start, count = (
            (hunk.new_start, hunk.new_lines)
            if new_side
            else (hunk.old_start, hunk.old_lines)
        )
        lines.update(range(start, start + count))
    return lines


def _compress(lines: list[int]) -> list[list[int]]:
    ranges: list[list[int]] = []
    for line in lines:
        if ranges and ranges[-1][1] == line - 1:
            ranges[-1][1] = line
        else:
            ranges.append([line, line])
    return ranges


@dataclass(slots=True)
class ChangedSymbol:
    id: str
    old_id: str | None
    status: str  # added | modified | deleted | moved
    symbol: Symbol


# ------------------------------------------------------------------------ main


def _list_changes(
    repo_root: Path, revisions: list[str], *, untracked: bool
) -> list[FileChange]:
    names = _git(
        repo_root, "diff", "--name-status", "-z", "-M", "--no-ext-diff", *revisions
    )
    changes = parse_name_status(names)
    patch = _git(
        repo_root,
        "diff",
        "-U0",
        "-M",
        "--no-color",
        "--no-ext-diff",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        *revisions,
    ).decode("utf-8", errors="replace")
    hunks = parse_unified_hunks(patch)
    for change in changes:
        found = hunks.get(change.path) or (
            hunks.get(change.old_path) if change.old_path else None
        )
        if found:
            change.hunks, change.binary = found
    if untracked:
        listed = _git(repo_root, "ls-files", "-z", "--others", "--exclude-standard")
        known = {c.path for c in changes}
        for raw in listed.split(b"\0"):
            rel = raw.decode("utf-8", errors="replace")
            if not rel or rel in known:
                continue
            try:
                count = len((repo_root / rel).read_bytes().splitlines())
            except OSError:
                continue
            changes.append(
                FileChange(rel, None, "added", [Hunk(0, 0, 1, count)] if count else [])
            )
    return [
        c
        for c in changes
        if not c.path.startswith(".repo_wiki/")
        and not (c.old_path or "").startswith(".repo_wiki/")
    ]


def detect_changes(
    repo_root: Path,
    config: dict[str, object],
    *,
    mode: str = "worktree",
    base: str | None = None,
    allow_stale: bool = False,
) -> dict[str, object]:
    """Changed files, the symbols they touch, and each symbol's direct callers."""
    inside = _git(repo_root, "rev-parse", "--is-inside-work-tree", check=False)
    if inside.decode().strip() != "true":
        raise GitError(f"repository root is not a git work tree: {repo_root}")
    head = _rev(repo_root, "HEAD")
    if mode == "base":
        if base is None:
            raise GitError("--base needs a git ref")
        base_commit = _rev(repo_root, base)
        if base_commit is None:
            raise GitError(f"missing or invalid git ref {base!r}")
        merge_base = (
            _git(repo_root, "merge-base", base_commit, head, check=False)
            .decode()
            .strip()
            if head
            else ""
        )
        old_rev = merge_base or base_commit
        revisions = [old_rev]
    else:
        old_rev = head or EMPTY_TREE
        revisions = ["--cached", old_rev] if mode == "staged" else [old_rev]
    changes = _list_changes(repo_root, revisions, untracked=mode != "staged")
    dirty = parse_name_status(_git(repo_root, "diff", "--name-status", "-z", old_rev))
    ignore = {c.path for c in changes} | {c.old_path for c in changes if c.old_path}
    ignore |= {c.path for c in dirty} | {c.old_path for c in dirty if c.old_path}
    if mode == "staged":
        listed = _git(repo_root, "ls-files", "-z", "--others", "--exclude-standard")
        ignore |= {r.decode("utf-8", "replace") for r in listed.split(b"\0") if r}

    loaded = load_code_graph(
        repo_root,
        config=config,
        allow_stale=allow_stale,
        ignore_stale=ignore,
        finalize=False,
    )
    graph = loaded.graph

    files_out: list[dict[str, object]] = []
    changed: list[ChangedSymbol] = []
    module_level: list[dict[str, object]] = []
    for change in sorted(changes, key=lambda c: c.path):
        entry, symbols, outside, new_parsed = _analyze_file(
            repo_root, config, change, old_rev=old_rev, staged=mode == "staged"
        )
        files_out.append(entry)
        changed.extend(symbols)
        if outside:
            module_level.append({"path": change.path, "lines": outside})
        if entry["symbols_supported"] and entry["parse_error"] is None:
            if change.old_path and change.old_path != change.path:
                graph.replace_file(change.old_path, None)
            if change.status == "deleted":
                graph.replace_file(change.path, None)
            elif new_parsed is not None:
                graph.replace_file(change.path, new_parsed)
    graph.finalize()
    return _report(
        graph,
        loaded.to_dict(repo_root),
        mode,
        base,
        old_rev,
        files_out,
        changed,
        module_level,
    )


def _analyze_file(
    repo_root: Path,
    config: dict[str, object],
    change: FileChange,
    *,
    old_rev: str,
    staged: bool,
) -> tuple[
    dict[str, object], list[ChangedSymbol], list[list[int]], ParsedModule | None
]:
    entry: dict[str, object] = {
        "path": change.path,
        "old_path": change.old_path if change.old_path != change.path else None,
        "status": change.status,
        "binary": change.binary,
        "hunks": [h.to_dict() for h in change.hunks],
        "symbols_supported": False,
        "parse_error": None,
    }
    language = _extractable(change.path, config) or (
        _extractable(change.old_path, config) if change.old_path else None
    )
    if language is None or change.binary:
        return entry, [], [], None
    entry["symbols_supported"] = True

    new_parsed: ParsedModule | None = None
    new_text = ""
    if change.status != "deleted":
        if staged:
            data = _git(repo_root, "show", f":{change.path}", check=False)
            new_parsed = extract_text(change.path, data, config)
        else:
            data = (repo_root / change.path).read_bytes()
            new_parsed = extract_path(repo_root, change.path, config)
        new_text = data.decode("utf-8", errors="replace")
    old_parsed: ParsedModule | None = None
    old_text = ""
    if change.old_path and change.status != "added":
        data = _git(repo_root, "show", f"{old_rev}:{change.old_path}", check=False)
        old_text = data.decode("utf-8", errors="replace")
        old_parsed = extract_text(change.old_path, data, config)

    for parsed in (new_parsed, old_parsed):
        if parsed is not None and parsed.errors:
            first = parsed.errors[0]
            entry["parse_error"] = f"{first.path}:{first.line}: {first.message}"
            return entry, [], [], None

    new_symbols = new_parsed.symbols if new_parsed else []
    old_symbols = old_parsed.symbols if old_parsed else []
    new_ranges = _effective_ranges(new_symbols, new_text)
    old_ranges = _effective_ranges(old_symbols, old_text)
    touched_new, outside_new = _innermost(
        new_symbols, new_ranges, _line_set(change.hunks, new_side=True)
    )
    touched_old, _ = _innermost(
        old_symbols, old_ranges, _line_set(change.hunks, new_side=False)
    )
    if change.status == "deleted":
        touched_old = {s.symbol_id for s in old_symbols}
    old_by_qual = {s.qualname: s for s in old_symbols}
    new_by_qual = {s.qualname: s for s in new_symbols}
    new_by_id = {s.symbol_id: s for s in new_symbols}
    old_by_id = {s.symbol_id: s for s in old_symbols}

    result: dict[str, ChangedSymbol] = {}
    for symbol_id in sorted(touched_new):
        symbol = new_by_id[symbol_id]
        before = old_by_qual.get(symbol.qualname)
        result[symbol_id] = ChangedSymbol(
            symbol_id,
            before.symbol_id if before and before.symbol_id != symbol_id else None,
            "modified" if before else "added",
            symbol,
        )
    for symbol_id in sorted(touched_old):
        symbol = old_by_id[symbol_id]
        after = new_by_qual.get(symbol.qualname)
        if after is None:
            result[symbol_id] = ChangedSymbol(symbol_id, None, "deleted", symbol)
        elif after.symbol_id not in result:
            result[after.symbol_id] = ChangedSymbol(
                after.symbol_id,
                symbol_id if symbol_id != after.symbol_id else None,
                "modified",
                after,
            )
    if change.status == "renamed":
        for symbol in new_symbols:
            before = old_by_qual.get(symbol.qualname)
            if symbol.symbol_id not in result and before is not None:
                result[symbol.symbol_id] = ChangedSymbol(
                    symbol.symbol_id, before.symbol_id, "moved", symbol
                )
    text_lines = new_text.splitlines()
    meaningful = [
        line
        for line in outside_new
        if line <= len(text_lines)
        and text_lines[line - 1].strip()
        and not text_lines[line - 1].lstrip().startswith("#")
    ]
    return entry, list(result.values()), _compress(meaningful), new_parsed


def _symbol_entry(graph: CodeGraph, item: ChangedSymbol) -> dict[str, object]:
    symbol = item.symbol
    return {
        "id": item.id,
        "old_id": item.old_id,
        "status": item.status,
        "kind": symbol.kind,
        "name": symbol.name,
        "qualname": symbol.qualname,
        "path": symbol.path,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "is_test": is_test_path(symbol.path),
        "public_entry": graph.public_entry_kind(item.id)
        if item.id in graph.nodes
        else None,
    }


def _dangling(graph: CodeGraph, item: ChangedSymbol) -> tuple[list[str], list[str]]:
    """Sources still naming a deleted or moved symbol: (confident, possible) source IDs."""
    symbol = item.symbol
    confident: set[str] = set()
    possible: set[str] = set()
    for source, entries in graph.unresolved.items():
        if source not in graph.nodes:
            continue
        for unresolved in entries:
            if unresolved.external:
                continue
            if unresolved.name.rsplit(".", 1)[-1] != symbol.name:
                continue
            same_file_bare = (
                unresolved.name == symbol.name
                and graph.nodes[source].path == symbol.path
            )
            if same_file_bare or (
                unresolved.attempted
                and unresolved.attempted.endswith("." + symbol.qualname)
            ):
                confident.add(source)
            else:
                possible.add(source)
    return sorted(confident), sorted(possible - confident)


def _report(
    graph: CodeGraph,
    graph_info: dict[str, object],
    mode: str,
    base: str | None,
    old_rev: str,
    files_out: list[dict[str, object]],
    changed: list[ChangedSymbol],
    module_level: list[dict[str, object]],
) -> dict[str, object]:
    changed_ids = {c.id for c in changed} | {c.old_id for c in changed if c.old_id}
    symbols_out: list[dict[str, object]] = []
    caller_hits: list[Hit] = []
    possible_hits: list[Hit] = []
    broken: list[str] = []
    for item in sorted(
        changed, key=lambda c: (c.symbol.path, c.symbol.start_line, c.id)
    ):
        entry = _symbol_entry(graph, item)
        confident: list[dict[str, object]] = []
        possible: list[dict[str, object]] = []
        if item.id in graph.nodes and item.status != "deleted":
            for edge in graph.in_edges.get(item.id, []):
                if (
                    edge.type not in ("calls", "inherits")
                    or edge.source not in graph.nodes
                ):
                    continue
                caller = {
                    **node_summary(graph, graph.nodes[edge.source]),
                    "edge": edge.to_dict(),
                    "changed": edge.source in changed_ids,
                }
                hit = Hit(edge.source, 1, item.id, edge)
                if edge.resolution == CONFIDENT:
                    confident.append(caller)
                    if edge.source not in changed_ids:
                        caller_hits.append(hit)
                elif edge.resolution == HEURISTIC:
                    possible.append(caller)
                    if edge.source not in changed_ids:
                        possible_hits.append(hit)
        if item.status in ("deleted", "moved"):
            sure, maybe = _dangling(graph, item)
            for source, bucket, resolution in (
                *((s, confident, CONFIDENT) for s in sure),
                *((s, possible, HEURISTIC) for s in maybe),
            ):
                bucket.append(
                    {
                        **node_summary(graph, graph.nodes[source]),
                        "edge": {
                            "type": "calls",
                            "resolution": resolution,
                            "basis": "dangling",
                            "name": item.symbol.name,
                        },
                        "changed": source in changed_ids,
                    }
                )
                if source in changed_ids:
                    continue
                if resolution == CONFIDENT:
                    broken.append(source)
            caller_hits.extend(
                Hit(s, 1, item.id, _placeholder_edge(s, item))
                for s in sure
                if s not in changed_ids
            )
            possible_hits.extend(
                Hit(s, 1, item.id, _placeholder_edge(s, item))
                for s in maybe
                if s not in changed_ids
            )
        entry["callers"] = {"confident": confident, "possible": possible}
        symbols_out.append(entry)

    targets = [c.id for c in changed if c.id in graph.nodes]
    risk = assess_risk(graph, targets, _unique(caller_hits))
    with_possible = assess_risk(graph, targets, _unique([*caller_hits, *possible_hits]))
    level, level_possible = risk.level, with_possible.level
    reasons = list(risk.reasons)
    if broken:
        reasons.append(
            f"{len(set(broken))} caller(s) still reference a deleted or moved symbol"
        )
        # A confident caller of a symbol that no longer exists breaks for certain.
        level = max(level, "HIGH", key=RISK_LEVELS.index)
        level_possible = max(level_possible, "HIGH", key=RISK_LEVELS.index)
    by_status: dict[str, int] = {}
    for item in changed:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    return {
        "schema": CHANGES_SCHEMA,
        "mode": mode,
        "base": base,
        "base_commit": old_rev if old_rev != EMPTY_TREE else None,
        "graph": graph_info,
        "files": files_out,
        "changed_symbols": symbols_out,
        "module_level_changes": module_level,
        "summary": {
            "files": len(files_out),
            "changed_symbols": len(changed),
            "by_status": dict(sorted(by_status.items())),
            "affected_callers": {
                "confident": len({h.node_id for h in caller_hits}),
                "possible": len(
                    {h.node_id for h in possible_hits}
                    - {h.node_id for h in caller_hits}
                ),
            },
            "dangling_references": len(set(broken)),
            "modules_reached": risk.modules_reached,
            "public_entry_points": risk.public_entry_points,
            "risk": level,
            "risk_with_possible": level_possible,
            "risk_reasons": reasons,
        },
    }


def _placeholder_edge(source: str, item: ChangedSymbol) -> Edge:
    return Edge(source, item.id, "calls", CONFIDENT, "dangling", item.symbol.name)


def _unique(hits: list[Hit]) -> list[Hit]:
    seen: dict[str, Hit] = {}
    for hit in hits:
        seen.setdefault(hit.node_id, hit)
    return list(seen.values())
