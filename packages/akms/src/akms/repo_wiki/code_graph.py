"""In-memory code graph for ``context``, ``impact`` and ``changes`` (loaded once, both directions).

The on-disk ``symbol_graph.json`` resolves call names repository-wide by name alone. This
module keeps the graph's nodes and per-symbol call names, then re-resolves each name the way
Python itself would look it up, using only what the graph already records:

==========  ============================================================  ==========
basis       evidence                                                      resolution
==========  ============================================================  ==========
scope       a function nested in an enclosing function of the caller      CONFIDENT
local       a top-level definition in the caller's own module             CONFIDENT
import      the caller's module imports the name (module- or function-     CONFIDENT
            level import, ``as`` aliases, one re-export hop per package)
self        ``self.m`` / ``cls.m`` found on the enclosing class or a      CONFIDENT
            confidently resolved base class
constructor a call of class ``C`` also reaches ``C.__init__``               as the call
receiver    ``x.m`` where ``x = C(...)`` or ``x: C`` in the caller: ``C.m``   CONFIDENT if
            (base classes walked); several bound classes give HEURISTIC     one target
dispatch    ``TABLE[key]`` / ``TABLE.get(key)`` on a module-level dict of   HEURISTIC
            callables: every value of the table
name        only a name match: no import or definition explains it          HEURISTIC
attribute   ``obj.m`` with an unknown receiver; methods named ``m``         HEURISTIC
==========  ============================================================  ==========

``receiver`` and ``dispatch`` links are *inferred* (``provenance: inferred``): they rest on a
pattern, not on a call written as such. A dispatch link is never CONFIDENT. A receiver bound
only to classes outside the repository (``p = argparse.ArgumentParser()``) is external.

Rust, C++ and Julia sources carry no import bindings, so they keep the graph's rule: one
name match is CONFIDENT (basis ``name``), several are HEURISTIC. Calls into modules that are
not part of the repository are *external* and produce no edge. Nothing here calls a model.

Unknown extra node or edge fields in ``symbol_graph.json`` are ignored.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, cast

from akms.repo_wiki.config import load_config
from akms.repo_wiki.errors import RepoWikiError
from akms.repo_wiki.graph import INFERRED, STATIC
from akms.repo_wiki.hashing import sha256_file
from akms.repo_wiki.models import ParsedModule, Symbol
from akms.repo_wiki.scanner import (
    LANGUAGE_BY_SUFFIX,
    _enabled_language_globs,
    matches_any,
    read_gitignore,
)

DEFAULT_OUTPUT_DIR = ".repo_wiki/generated"
GRAPH_FILENAME = "symbol_graph.json"
MANIFEST_RELPATH = ".repo_wiki/manifest.json"
BUILD_ERRORS_RELPATH = ".repo_wiki/build_errors.json"

CONFIDENT = "CONFIDENT"
HEURISTIC = "HEURISTIC"

#: An ``obj.m`` call with an unknown receiver links to the methods named ``m`` only when there
#: are at most this many; above it the name is too common to say anything.
ATTRIBUTE_CANDIDATE_LIMIT = 4

#: Method names of built-in types and ``pathlib.Path``: ``x.append()`` says nothing about
#: which repository method (if any) runs, so these never produce an ``attribute`` link.
BUILTIN_METHOD_NAMES = frozenset(
    name
    for kind in (list, dict, set, frozenset, tuple, str, bytes, int, float, Path)
    for name in dir(kind)
)

#: Path components and file names that mark a test file.
TEST_DIR_NAMES = frozenset({"tests", "test"})

_EXTERNAL = "<external>"
_LINE_SUFFIX = re.compile(r"@L\d+$")
_JOINERS = {"python": ".", "julia": ".", "rust": "::", "cpp": "::"}


def rebuild_command(repo_root: Path) -> str:
    """The command that refreshes the symbol graph alone (fastest rebuild)."""
    return (
        f"repo-wiki --repo-root {repo_root} build --changed-only "
        "--no-summaries --no-index"
    )


class GraphUnavailableError(RepoWikiError):
    """The symbol graph is missing, unreadable or stale; the message says how to rebuild."""

    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(slots=True)
class Node:
    """One graph node: a symbol (function, class, method, constant) or a module."""

    id: str
    kind: str
    path: str
    start_line: int
    end_line: int
    language: str
    qualname: str
    name: str
    module_id: str
    parent_id: str | None

    @property
    def is_module(self) -> bool:
        return self.kind == "module"


@dataclass(slots=True)
class Edge:
    """A resolved dependency ``source -> target`` (``calls``, ``inherits`` or ``imports``)."""

    source: str
    target: str
    type: str
    resolution: str
    basis: str
    dst_name: str
    candidates: tuple[str, ...] = ()
    provenance: str = STATIC

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": self.type,
            "resolution": self.resolution,
            "basis": self.basis,
            "name": self.dst_name,
            "provenance": self.provenance,
        }
        if self.candidates:
            data["candidates"] = list(self.candidates)
        return data


@dataclass(slots=True)
class Unresolved:
    """A call name with no edge: ``external`` (outside the repository) or unknown."""

    source: str
    name: str
    external: bool
    attempted: str | None = None  # the dotted import target that did not resolve


@dataclass(slots=True)
class _FileUnit:
    module: Node
    bindings: dict[str, str]
    imports: list[str]
    symbols: list[Node]
    records: list[tuple[str, str, str]]  # (source id, called/base name, edge type)
    receivers: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    table_refs: dict[str, list[str]] = field(default_factory=dict)
    dispatch: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class Freshness:
    """Files whose content differs from what the graph was built from."""

    changed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def stale(self) -> bool:
        return bool(self.changed or self.added or self.removed)

    def to_dict(self) -> dict[str, object]:
        return {
            "stale": self.stale,
            "changed": self.changed,
            "added": self.added,
            "removed": self.removed,
        }


def is_test_path(path: str) -> bool:
    """True for files under ``tests/``/``test/`` and ``test_*.py``, ``*_test.py``, ``conftest.py``."""
    parts = PurePosixPath(path).parts
    if not parts:
        return False
    name = parts[-1]
    stem = name.rsplit(".", 1)[0]
    return (
        any(part in TEST_DIR_NAMES for part in parts[:-1])
        or stem.startswith("test_")
        or stem.endswith("_test")
        or name == "conftest.py"
    )


def _line(value: object) -> int:
    """A 1-based line number from a JSON value (anything unusable reads as line 1)."""
    if isinstance(value, bool):
        return 1
    if isinstance(value, int):
        return max(value, 1)
    if isinstance(value, str) and value.isdigit():
        return max(int(value), 1)
    return 1


def _language_of(node_id: str, path: str) -> str:
    if "::" in node_id and ":" in node_id.split("::", 1)[0]:
        return node_id.split(":", 1)[0]
    return LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.lower(), "text")


def _split_qualname(node_id: str, language: str) -> tuple[str, str]:
    """``<lang>:<path>::<qualname>[@L<n>]`` -> ``(qualname, name)``."""
    qualname = (
        _LINE_SUFFIX.sub("", node_id.split("::", 1)[1]) if "::" in node_id else ""
    )
    joiner = _JOINERS.get(language, ".")
    return qualname, qualname.rsplit(joiner, 1)[-1] if qualname else ""


class CodeGraph:
    """Symbol graph with forward and reverse adjacency built once in memory."""

    def __init__(self) -> None:
        self._files: dict[str, _FileUnit] = {}
        self.nodes: dict[str, Node] = {}
        self.out_edges: dict[str, list[Edge]] = {}
        self.in_edges: dict[str, list[Edge]] = {}
        self.unresolved: dict[str, list[Unresolved]] = {}
        self.external_imports: dict[str, list[str]] = {}
        self.children: dict[str, list[str]] = {}
        self.module_members: dict[str, list[str]] = {}
        self.module_by_path: dict[str, str] = {}
        self.bindings: dict[str, dict[str, str]] = {}
        self.receivers: dict[str, dict[str, list[str]]] = {}
        self.dispatch: dict[str, dict[str, list[str]]] = {}
        self._by_name: dict[str, list[str]] = {}
        self._dotted_modules: dict[str, str] = {}
        self._module_names: dict[str, str] = {}
        self._import_index: dict[str, tuple[dict[str, set[str]], set[str]]] = {}
        self._exported: set[str] | None = None
        self._finalized = False

    # ------------------------------------------------------------------ loading

    @classmethod
    def from_symbol_graph(cls, data: dict[str, object]) -> "CodeGraph":
        """Build from the ``symbol_graph.json`` payload; unknown extra fields are ignored."""
        graph = cls()
        raw_nodes = data.get("nodes")
        raw_edges = data.get("edges")
        if not isinstance(raw_nodes, dict) or not isinstance(raw_edges, list):
            raise ValueError("symbol graph has no 'nodes' mapping or 'edges' list")
        parents: dict[str, str] = {}
        modules_of: dict[str, str] = {}
        records: dict[str, list[tuple[str, str, str]]] = {}
        imports: dict[str, list[str]] = {}
        for edge in raw_edges:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source", ""))
            kind = edge.get("type")
            name = str(edge.get("dst_name") or edge.get("target") or "")
            if kind == "belongs_to":
                parents[source] = str(edge.get("target"))
            elif kind == "defined_in":
                modules_of[source] = str(edge.get("target"))
            elif kind in ("calls", "inherits") and name:
                records.setdefault(source, []).append((source, name, str(kind)))
            elif kind == "imports" and name:
                imports.setdefault(source, []).append(name)
        units: dict[str, _FileUnit] = {}
        symbol_nodes: list[tuple[str, dict[str, object]]] = []
        for node_id, raw in raw_nodes.items():
            if not isinstance(raw, dict):
                continue
            if raw.get("kind") == "module":
                path = str(raw.get("path", ""))
                language = _language_of(str(node_id), path)
                bindings = raw.get("bindings")
                units[path] = _FileUnit(
                    module=Node(
                        id=str(node_id),
                        kind="module",
                        path=path,
                        start_line=1,
                        end_line=_line(raw.get("end_line")),
                        language=language,
                        qualname="",
                        name=str(node_id).rsplit(".", 1)[-1],
                        module_id=str(node_id),
                        parent_id=None,
                    ),
                    bindings=(
                        {str(k): str(v) for k, v in bindings.items()}
                        if isinstance(bindings, dict)
                        else {}
                    ),
                    imports=sorted(dict.fromkeys(imports.get(str(node_id), []))),
                    symbols=[],
                    records=[],
                    dispatch=_name_lists(raw.get("dispatch")),
                )
            else:
                symbol_nodes.append((str(node_id), raw))
        for node_id, raw in symbol_nodes:
            path = str(raw.get("path", ""))
            unit = units.get(path)
            if unit is None:
                continue
            language = _language_of(node_id, path)
            qualname, name = _split_qualname(node_id, language)
            unit.symbols.append(
                Node(
                    id=node_id,
                    kind=str(raw.get("kind", "")),
                    path=path,
                    start_line=_line(raw.get("start_line")),
                    end_line=_line(raw.get("end_line")),
                    language=language,
                    qualname=qualname,
                    name=name,
                    module_id=modules_of.get(node_id, unit.module.id),
                    parent_id=parents.get(node_id),
                )
            )
            unit.records.extend(records.get(node_id, []))
            receivers = _name_lists(raw.get("receivers"))
            if receivers:
                unit.receivers[node_id] = receivers
            table_refs = raw.get("table_refs")
            if isinstance(table_refs, list) and table_refs:
                unit.table_refs[node_id] = [str(v) for v in table_refs]
        graph._files = units
        return graph

    def replace_file(self, path: str, parsed: ParsedModule | None) -> None:
        """Swap one file's nodes and call names for *parsed* (``None`` removes the file)."""
        self._finalized = False
        self._files.pop(path, None)
        if parsed is not None:
            self._files[parsed.source_file.path] = unit_from_parsed(parsed)

    # --------------------------------------------------------------- finalizing

    def finalize(self) -> "CodeGraph":
        """Index nodes and resolve every recorded name; idempotent."""
        if self._finalized:
            return self
        self.nodes = {}
        self.children = {}
        self.module_members = {}
        self.module_by_path = {}
        self.bindings = {}
        self.receivers = {}
        self.dispatch = {}
        self._by_name = {}
        self._import_index = {}
        self._exported = None
        for path, unit in self._files.items():
            self.nodes[unit.module.id] = unit.module
            self.module_by_path[path] = unit.module.id
            self.bindings[unit.module.id] = unit.bindings
            if unit.dispatch:
                self.dispatch[unit.module.id] = unit.dispatch
            self.receivers.update(unit.receivers)
            for node in unit.symbols:
                self.nodes[node.id] = node
        for unit in self._files.values():
            for node in unit.symbols:
                if node.parent_id and node.parent_id in self.nodes:
                    self.children.setdefault(node.parent_id, []).append(node.id)
                else:
                    node.parent_id = None
                self.module_members.setdefault(node.module_id, []).append(node.id)
                for key in (node.name, node.qualname):
                    bucket = self._by_name.setdefault(key, [])
                    if node.id not in bucket:
                        bucket.append(node.id)
        for bucket in self._by_name.values():
            bucket.sort()
        self._index_python_modules()
        self._resolve_all()
        self._finalized = True
        return self

    def _index_python_modules(self) -> None:
        """Dotted import name -> module ID: full path, after ``src``, and the package chain."""
        modules = [
            unit.module
            for unit in self._files.values()
            if unit.module.language == "python"
        ]
        package_dirs = {
            str(PurePosixPath(m.path).parent)
            for m in modules
            if PurePosixPath(m.path).name == "__init__.py"
        }
        exact: dict[str, str] = {m.id: m.id for m in modules}
        aliases: dict[str, set[str]] = {}
        for module in modules:
            parts = module.id.split(".")
            names: set[str] = set()
            if "src" in parts[:-1]:
                cut = len(parts) - 1 - parts[::-1].index("src")
                if parts[cut + 1 :]:
                    names.add(".".join(parts[cut + 1 :]))
            pure = PurePosixPath(module.path)
            directory = pure.parent
            chain = [] if pure.name == "__init__.py" else [pure.stem]
            while str(directory) in package_dirs and str(directory) != ".":
                chain.insert(0, directory.name)
                directory = directory.parent
            if chain:
                names.add(".".join(chain))
            for name in names:
                aliases.setdefault(name, set()).add(module.id)
        dotted = dict(exact)
        for name, owners in aliases.items():
            if name not in dotted and len(owners) == 1:
                dotted[name] = next(iter(owners))
        self._dotted_modules = dotted
        shortest: dict[str, str] = {}
        for name, module_id in dotted.items():
            best = shortest.get(module_id)
            if best is None or (name.count("."), name) < (best.count("."), best):
                shortest[module_id] = name
        self._module_names = shortest

    # --------------------------------------------------------------- resolution

    def _resolve_all(self) -> None:
        self.out_edges = {}
        self.in_edges = {}
        self.unresolved = {}
        self.external_imports = {}
        seen: dict[tuple[str, str, str], Edge] = {}
        for unit in self._files.values():
            module = unit.module
            for raw in unit.imports:
                target = self.resolve_dotted(_absolute(raw, module))
                if target is None or target == _EXTERNAL:
                    self.external_imports.setdefault(module.id, []).append(raw)
                    continue
                target_module = self.nodes[target].module_id
                if target_module != module.id:
                    self._add(
                        seen,
                        Edge(
                            module.id,
                            target_module,
                            "imports",
                            CONFIDENT,
                            "import",
                            raw,
                        ),
                    )
        # Bases first: ``self.m`` lookups walk the confidently resolved ``inherits`` edges.
        for wanted in ("inherits", "calls"):
            for unit in self._files.values():
                descendant_calls = (
                    self._descendant_call_names(unit) if wanted == "calls" else {}
                )
                for source, name, kind in unit.records:
                    if kind != wanted:
                        continue
                    node = self.nodes.get(source)
                    if node is None:
                        continue
                    # A class's call list repeats every call made inside its methods.
                    if node.kind == "class" and name in descendant_calls.get(
                        source, ()
                    ):
                        continue
                    outcome = self._resolve_name(node, name, kind)
                    if isinstance(outcome, Unresolved):
                        self.unresolved.setdefault(source, []).append(outcome)
                        continue
                    for edge in outcome:
                        self._add(seen, edge)
                if wanted == "calls":
                    for source, refs in sorted(unit.table_refs.items()):
                        node = self.nodes.get(source)
                        if node is None:
                            continue
                        for ref in refs:
                            for edge in self._dispatch_edges(node, ref):
                                self._add(seen, edge)
        for edges in (self.out_edges, self.in_edges):
            for bucket in edges.values():
                bucket.sort(key=lambda e: (e.type, e.source, e.target))

    def _descendant_call_names(self, unit: _FileUnit) -> dict[str, set[str]]:
        by_source: dict[str, set[str]] = {}
        for source, name, kind in unit.records:
            if kind == "calls":
                by_source.setdefault(source, set()).add(name)
        result: dict[str, set[str]] = {}
        for node in unit.symbols:
            if node.kind != "class":
                continue
            names: set[str] = set()
            stack = list(self.children.get(node.id, []))
            while stack:
                child = stack.pop()
                names |= by_source.get(child, set())
                stack.extend(self.children.get(child, []))
            result[node.id] = names
        return result

    def _add(self, seen: dict[tuple[str, str, str], Edge], edge: Edge) -> None:
        if edge.source == edge.target:
            return
        key = (edge.source, edge.target, edge.type)
        previous = seen.get(key)
        if previous is not None:
            if previous.resolution == CONFIDENT or edge.resolution != CONFIDENT:
                return
            self.out_edges[edge.source].remove(previous)
            self.in_edges[edge.target].remove(previous)
        seen[key] = edge
        self.out_edges.setdefault(edge.source, []).append(edge)
        self.in_edges.setdefault(edge.target, []).append(edge)

    def _resolve_name(
        self, node: Node, name: str, kind: str
    ) -> list[Edge] | Unresolved:
        if node.language != "python":
            return self._name_match(node, name, kind, strict=False)
        name = name.split("[", 1)[0]  # Generic[T] -> Generic
        if not name:
            return Unresolved(node.id, name, external=False)
        head, _, rest = name.partition(".")
        if not rest:
            return self._resolve_bare(node, name, kind)
        if kind == "calls" and head not in ("self", "cls"):
            inferred = self._receiver_edges(node, head, rest, name)
            if inferred is not None:
                return inferred
        if head in ("self", "cls"):
            owner = self._enclosing_class(node)
            if owner is not None and "." not in rest:
                member = self.lookup_member(owner, rest)
                if member is not None:
                    return self._edges(node, member, kind, CONFIDENT, "self", name)
            return self._attribute_match(node, name, kind)
        base = self._resolve_head(node, head)
        if base is None:
            return self._attribute_match(node, name, kind)
        target_id, basis, dotted = base
        if target_id == _EXTERNAL:
            return Unresolved(node.id, name, external=True)
        full = f"{dotted}.{rest}" if dotted else None
        found = self.resolve_dotted(full) if full else None
        if (found is None or found == _EXTERNAL) and target_id in self.nodes:
            found = self._walk_members(target_id, rest.split("."))
        if found is None or found == _EXTERNAL:
            return Unresolved(node.id, name, external=False, attempted=full)
        return self._edges(node, found, kind, CONFIDENT, basis, name)

    def _receiver_types(self, node: Node, var: str) -> list[str] | None:
        """Names *var* is bound to in *node* or an enclosing function (closest scope first)."""
        scope: Node | None = node
        while scope is not None and scope.kind in ("function", "method"):
            bound = self.receivers.get(scope.id, {}).get(var)
            if bound:
                return bound
            scope = self.nodes.get(scope.parent_id) if scope.parent_id else None
        return None

    def _receiver_edges(
        self, node: Node, var: str, rest: str, name: str
    ) -> list[Edge] | Unresolved | None:
        """``var.m()`` where *var* was bound to ``C(...)``/``C``: ``C.m``, provenance inferred.

        ``None`` when *var* is not a typed local (the usual rules then apply). CONFIDENT
        only when every bound name is a repository class and they all lead to one method.
        """
        if "." in rest or node.language != "python":
            return None
        bound = self._receiver_types(node, var)
        if not bound:
            return None
        targets: set[str] = set()
        external = 0
        unknown = 0
        for type_name in bound:
            outcome = self._resolve_name(node, type_name, "inherits")
            if isinstance(outcome, Unresolved):
                external += outcome.external
                unknown += not outcome.external
                continue
            classes = [
                e.target
                for e in outcome
                if e.resolution == CONFIDENT
                and e.target in self.nodes
                and self.nodes[e.target].kind == "class"
            ]
            if not classes:
                unknown += 1
                continue
            for owner in classes:
                member = self.lookup_member(owner, rest)
                if member is None:
                    unknown += 1
                else:
                    targets.add(member)
        if not targets:
            if external and not unknown:
                return Unresolved(node.id, name, external=True)
            return None
        ordered = tuple(sorted(targets))
        if len(ordered) == 1 and not unknown and not external:
            return [
                Edge(
                    node.id,
                    ordered[0],
                    "calls",
                    CONFIDENT,
                    "receiver",
                    name,
                    provenance=INFERRED,
                )
            ]
        return [
            Edge(
                node.id,
                target,
                "calls",
                HEURISTIC,
                "receiver",
                name,
                ordered,
                provenance=INFERRED,
            )
            for target in ordered
        ]

    def _dispatch_table(self, node: Node, ref: str) -> tuple[Node, list[str]] | None:
        """The dispatch table *ref* names in *node*'s module: (owning module, values)."""
        local = self.dispatch.get(node.module_id, {}).get(ref)
        module = self.nodes.get(node.module_id)
        if local is not None and module is not None:
            return module, local
        target = self._import_target(node.module_id, ref)
        if not target or "." not in target:
            return None
        owner_dotted, _, table = target.rpartition(".")
        owner = self.resolve_dotted(owner_dotted)
        if owner is None or owner == _EXTERNAL or not self.nodes[owner].is_module:
            return None
        values = self.dispatch.get(owner, {}).get(table)
        return (self.nodes[owner], values) if values is not None else None

    def _dispatch_edges(self, node: Node, ref: str) -> list[Edge]:
        """HEURISTIC ``calls`` from *node* to every callable in the table *ref* names."""
        found = self._dispatch_table(node, ref)
        if found is None:
            return []
        module, values = found
        targets: set[str] = set()
        for value in values:
            outcome = self._resolve_name(module, value, "calls")
            if isinstance(outcome, Unresolved):
                continue
            targets.update(
                e.target
                for e in outcome
                if e.resolution == CONFIDENT and e.target in self.nodes
            )
        targets.discard(node.id)
        ordered = tuple(sorted(targets))
        return [
            Edge(
                node.id,
                target,
                "calls",
                HEURISTIC,
                "dispatch",
                ref,
                ordered,
                provenance=INFERRED,
            )
            for target in ordered
        ]

    def _resolve_bare(
        self, node: Node, name: str, kind: str
    ) -> list[Edge] | Unresolved:
        module_path = node.path
        scope: Node | None = node
        while scope is not None:
            if scope.kind in ("function", "method"):
                candidate = f"python:{module_path}::{scope.qualname}.{name}"
                if candidate in self.nodes:
                    return self._edges(node, candidate, kind, CONFIDENT, "scope", name)
            scope = self.nodes.get(scope.parent_id) if scope.parent_id else None
        local = f"python:{module_path}::{name}"
        if local in self.nodes:
            return self._edges(node, local, kind, CONFIDENT, "local", name)
        target = self._import_target(node.module_id, name)
        if target is not None:
            found = self.resolve_dotted(target)
            if found == _EXTERNAL:
                return Unresolved(node.id, name, external=True)
            if found is None:
                return Unresolved(node.id, name, external=False, attempted=target)
            return self._edges(node, found, kind, CONFIDENT, "import", name)
        return self._name_match(node, name, kind, strict=True)

    def _resolve_head(
        self, node: Node, head: str
    ) -> tuple[str, str, str | None] | None:
        """Resolve the first dotted part: ``(target id or external, basis, dotted path)``."""
        local = f"python:{node.path}::{head}"
        if local in self.nodes:
            return local, "local", None
        target = self._import_target(node.module_id, head)
        if target is None:
            return None
        found = self.resolve_dotted(target)
        if found == _EXTERNAL:
            return _EXTERNAL, "import", target
        return (found or "", "import", target)

    def _import_target(self, module_id: str, name: str) -> str | None:
        """The dotted target *name* is imported as in *module_id* (module or function scope)."""
        bound = self.bindings.get(module_id, {}).get(name)
        if bound:
            return bound
        index = self._import_index.get(module_id)
        if index is None:
            index = self._index_imports(module_id)
            self._import_index[module_id] = index
        by_last, heads = index
        exact = by_last.get(name)
        if exact:
            return next(iter(exact)) if len(exact) == 1 else None
        return name if name in heads else None

    def _index_imports(self, module_id: str) -> tuple[dict[str, set[str]], set[str]]:
        """Per module: last dotted part -> absolute targets, and top-level import heads."""
        node = self.nodes.get(module_id)
        unit = self._files.get(node.path) if node is not None else None
        by_last: dict[str, set[str]] = {}
        heads: set[str] = set()
        if unit is None:
            return by_last, heads
        for raw in unit.imports:
            last = raw.lstrip(".").rsplit(".", 1)[-1]
            by_last.setdefault(last, set()).add(_absolute(raw, unit.module))
            if not raw.startswith("."):
                heads.add(raw.split(".", 1)[0])
        return by_last, heads

    def _name_match(
        self, node: Node, name: str, kind: str, *, strict: bool
    ) -> list[Edge] | Unresolved:
        candidates = [c for c in self._by_name.get(name, []) if c != node.id]
        if strict:
            # A bare Python name can only reach a top-level definition.
            candidates = [c for c in candidates if self.nodes[c].parent_id is None]
        if kind == "inherits":
            candidates = [c for c in candidates if self.nodes[c].kind == "class"]
        if not candidates:
            return Unresolved(node.id, name, external=False)
        if len(candidates) == 1 and not strict:
            return self._edges(node, candidates[0], kind, CONFIDENT, "name", name)
        edges: list[Edge] = []
        for candidate in candidates:
            edges.extend(
                self._edges(
                    node, candidate, kind, HEURISTIC, "name", name, tuple(candidates)
                )
            )
        return edges

    def _attribute_match(
        self, node: Node, name: str, kind: str
    ) -> list[Edge] | Unresolved:
        method = name.rsplit(".", 1)[-1]
        if kind != "calls" or method in BUILTIN_METHOD_NAMES or method.startswith("__"):
            return Unresolved(node.id, name, external=False)
        candidates = [
            c
            for c in self._by_name.get(method, [])
            if c != node.id
            and self.nodes[c].kind == "method"
            and self.nodes[c].parent_id is not None
            and self.nodes[self.nodes[c].parent_id or ""].kind == "class"
        ]
        if not candidates or len(candidates) > ATTRIBUTE_CANDIDATE_LIMIT:
            return Unresolved(node.id, name, external=False)
        return [
            Edge(node.id, c, kind, HEURISTIC, "attribute", name, tuple(candidates))
            for c in candidates
        ]

    def _edges(
        self,
        node: Node,
        target: str,
        kind: str,
        resolution: str,
        basis: str,
        name: str,
        candidates: tuple[str, ...] = (),
    ) -> list[Edge]:
        target_node = self.nodes.get(target)
        if target_node is not None and target_node.is_module:
            return []  # a module is imported, not called or inherited
        edges = [Edge(node.id, target, kind, resolution, basis, name, candidates)]
        if (
            kind == "calls"
            and target_node is not None
            and target_node.kind == "class"
            and target_node.language == "python"
        ):
            init = self.lookup_member(target, "__init__", inherited=False)
            if init is not None:
                edges.append(
                    Edge(
                        node.id, init, kind, resolution, "constructor", name, candidates
                    )
                )
        return edges

    # ------------------------------------------------------------------ lookups

    def resolve_dotted(self, dotted: str | None, _hops: int = 0) -> str | None:
        """Python dotted name -> node ID, ``None`` (in-repo, unknown) or the external marker."""
        if not dotted:
            return None
        parts = dotted.split(".")
        for cut in range(len(parts), 0, -1):
            module_id = self._dotted_modules.get(".".join(parts[:cut]))
            if module_id is None:
                continue
            rest = parts[cut:]
            if not rest:
                return module_id
            module = self.nodes[module_id]
            candidate = f"python:{module.path}::{'.'.join(rest)}"
            if candidate in self.nodes:
                return candidate
            head = f"python:{module.path}::{rest[0]}"
            if head in self.nodes and self.nodes[head].kind == "class":
                return self._walk_members(head, rest[1:])
            target = self.bindings.get(module_id, {}).get(rest[0])
            if target and _hops < 4 and head not in self.nodes:
                return self.resolve_dotted(".".join([target, *rest[1:]]), _hops + 1)
            return None
        return _EXTERNAL

    def _walk_members(self, start: str, parts: list[str]) -> str | None:
        current = start
        for part in parts:
            found = self.lookup_member(current, part)
            if found is None:
                return None
            current = found
        return current

    def lookup_member(
        self, owner: str, name: str, *, inherited: bool = True
    ) -> str | None:
        """``owner.name`` on a class (then its confidently resolved bases, breadth-first)."""
        queue = [owner]
        visited: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            node = self.nodes.get(current)
            if node is None:
                continue
            joiner = _JOINERS.get(node.language, ".")
            candidate = f"{node.language}:{node.path}::{node.qualname}{joiner}{name}"
            if candidate in self.nodes:
                return candidate
            if not inherited:
                return None
            queue.extend(
                e.target
                for e in self.out_edges.get(current, [])
                if e.type == "inherits" and e.resolution == CONFIDENT
            )
        return None

    def _enclosing_class(self, node: Node) -> str | None:
        current = self.nodes.get(node.parent_id) if node.parent_id else None
        while current is not None:
            if current.kind == "class":
                return current.id
            current = self.nodes.get(current.parent_id) if current.parent_id else None
        return None

    def dotted_name(self, node_id: str) -> str | None:
        """The importable dotted name of a Python symbol or module (shortest registered)."""
        node = self.nodes.get(node_id)
        if node is None or node.language != "python":
            return None
        module_name = self._module_names.get(node.module_id)
        if module_name is None:
            return None
        return f"{module_name}.{node.qualname}" if node.qualname else module_name

    def find_by_name(self, name: str) -> list[str]:
        return list(self._by_name.get(name, []))

    def symbols_in(self, path: str) -> list[Node]:
        unit = self._files.get(path)
        return list(unit.symbols) if unit else []

    def module_imports(self, module_id: str) -> list[str]:
        unit = (
            self._files.get(self.nodes[module_id].path)
            if module_id in self.nodes
            else None
        )
        return list(unit.imports) if unit else []

    def exported_ids(self) -> set[str]:
        """Public names a package ``__init__`` defines or re-exports from its own subtree.

        An ``__init__`` importing from a sibling package is using the name, not exporting it.
        """
        if self._exported is None:
            exported: set[str] = set()
            for unit in self._files.values():
                if PurePosixPath(unit.module.path).name != "__init__.py":
                    continue
                package_dir = str(PurePosixPath(unit.module.path).parent)
                prefix = "" if package_dir == "." else package_dir + "/"
                for local, target in unit.bindings.items():
                    if local.startswith("_"):
                        continue
                    found = self.resolve_dotted(target)
                    if (
                        found
                        and found != _EXTERNAL
                        and not self.nodes[found].is_module
                        and self.nodes[found].path.startswith(prefix)
                    ):
                        exported.add(found)
                for node in unit.symbols:
                    if node.parent_id is None and not node.name.startswith("_"):
                        exported.add(node.id)
            self._exported = exported
        return self._exported

    def public_entry_kind(self, node_id: str) -> str | None:
        """``"cli"`` for CLI modules, ``"export"`` for package exports, else ``None``."""
        node = self.nodes.get(node_id)
        if node is None or is_test_path(node.path):
            return None
        pure = PurePosixPath(node.path)
        if pure.name in ("cli.py", "__main__.py") or "cli" in pure.parts[:-1]:
            return "cli"
        if node_id in self.exported_ids():
            return "export"
        return None


def unit_from_parsed(parsed: ParsedModule) -> _FileUnit:
    """Graph view of one freshly parsed module (same IDs as ``build_symbol_graph``)."""
    path = parsed.source_file.path
    language = parsed.source_file.language
    module = Node(
        id=parsed.module,
        kind="module",
        path=path,
        start_line=1,
        end_line=1,
        language=language,
        qualname="",
        name=parsed.module.rsplit(".", 1)[-1],
        module_id=parsed.module,
        parent_id=None,
    )
    symbols = [node_from_symbol(s, parsed.module) for s in parsed.symbols]
    records: list[tuple[str, str, str]] = []
    for symbol in parsed.symbols:
        records.extend((symbol.symbol_id, base, "inherits") for base in symbol.bases)
        records.extend((symbol.symbol_id, call, "calls") for call in symbol.calls)
    return _FileUnit(
        module=module,
        bindings=dict(parsed.import_bindings),
        imports=list(parsed.imports),
        symbols=symbols,
        records=records,
        receivers={
            s.symbol_id: {k: list(v) for k, v in s.receivers.items()}
            for s in parsed.symbols
            if s.receivers
        },
        table_refs={
            s.symbol_id: list(s.table_refs) for s in parsed.symbols if s.table_refs
        },
        dispatch={k: list(v) for k, v in parsed.dispatch_tables.items()},
    )


def node_from_symbol(symbol: Symbol, module_id: str) -> Node:
    return Node(
        id=symbol.symbol_id,
        kind=symbol.kind,
        path=symbol.path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        language=symbol.language.value,
        qualname=symbol.qualname,
        name=symbol.name,
        module_id=module_id,
        parent_id=symbol.parent_id,
    )


def _name_lists(value: object) -> dict[str, list[str]]:
    """``{name: [names]}`` from a JSON node field; malformed values read as empty."""
    if not isinstance(value, dict):
        return {}
    return {
        str(k): [str(v) for v in items]
        for k, items in value.items()
        if isinstance(items, list)
    }


def _absolute(raw: str, module: Node) -> str:
    """Resolve a leading-dot relative import against *module*'s package."""
    if not raw.startswith("."):
        return raw
    level = len(raw) - len(raw.lstrip("."))
    package = module.id.split(".")
    if PurePosixPath(module.path).name != "__init__.py":
        package = package[:-1]
    if level - 1 > len(package):
        return raw.lstrip(".")
    base = package[: len(package) - (level - 1)]
    tail = raw[level:]
    return ".".join([*base, *([tail] if tail else [])])


# --------------------------------------------------------------------- on disk


def graph_file(repo_root: Path, config: dict[str, object] | None = None) -> Path:
    """Where ``build`` writes the symbol graph (``generation.output_dir``)."""
    config = config if config is not None else load_config(repo_root)
    generation = config.get("generation")
    output_dir = (
        generation.get("output_dir", DEFAULT_OUTPUT_DIR)
        if isinstance(generation, dict)
        else DEFAULT_OUTPUT_DIR
    )
    return repo_root / str(output_dir) / GRAPH_FILENAME


def check_freshness(
    repo_root: Path,
    config: dict[str, object],
    graph_path: Path,
    *,
    ignore: Iterable[str] = (),
) -> Freshness:
    """Compare the sources the graph was built from (manifest hashes) with the tree.

    Only files modified after the graph was written are hashed, so the check costs one
    ``stat`` per tracked file plus one ``git ls-files`` (or a directory walk) for new files.
    """
    ignored = set(ignore)
    freshness = Freshness()
    manifest_path = repo_root / MANIFEST_RELPATH
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return freshness
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        return freshness
    built_at = graph_path.stat().st_mtime
    tracked: set[str] = set()
    for rel, entry in files.items():
        tracked.add(rel)
        if rel in ignored:
            continue
        path = repo_root / rel
        try:
            mtime = path.stat().st_mtime
        except OSError:
            freshness.removed.append(rel)
            continue
        if mtime > built_at and isinstance(entry, dict):
            if sha256_file(path) != entry.get("hash"):
                freshness.changed.append(rel)
    skip = tracked | ignored | _build_error_paths(repo_root)
    freshness.added.extend(_new_sources(repo_root, config, skip))
    freshness.changed.sort()
    freshness.added.sort()
    freshness.removed.sort()
    return freshness


def _build_error_paths(repo_root: Path) -> set[str]:
    try:
        errors = json.loads(
            (repo_root / BUILD_ERRORS_RELPATH).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return set()
    if not isinstance(errors, list):
        return set()
    return {str(e.get("path")) for e in errors if isinstance(e, dict)}


def _new_sources(
    repo_root: Path, config: dict[str, object], known: set[str]
) -> list[str]:
    """Files ``build`` would extract symbols from that are not in *known*."""
    from akms.repo_wiki.extract.registry import resolve_backend_name

    raw_scanner = config.get("scanner")
    scanner = cast(dict[str, Any], raw_scanner if isinstance(raw_scanner, dict) else {})
    include = [str(v) for v in scanner.get("include", [])]
    if include:
        include = include + _enabled_language_globs(config)
    exclude = [str(v) for v in scanner.get("exclude", [])]
    if scanner.get("respect_gitignore", True):
        exclude = exclude + read_gitignore(repo_root)
    routable = {
        suffix
        for suffix, language in LANGUAGE_BY_SUFFIX.items()
        if resolve_backend_name(language, config) is not None
    }
    listed = _git_listed_files(repo_root)
    if listed is None:
        from akms.repo_wiki.scanner import scan_repository

        sources, _ = scan_repository(repo_root, config)
        listed = [s.path for s in sources]
    return [
        rel
        for rel in listed
        if rel not in known
        and PurePosixPath(rel).suffix.lower() in routable
        and (not include or matches_any(rel, include))
        and not matches_any(rel, exclude)
        and (repo_root / rel).is_file()
        and not (repo_root / rel).is_symlink()
    ]


def _git_listed_files(repo_root: Path) -> list[str] | None:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            "git",
            "-C",
            str(repo_root),
            "-c",
            "core.quotepath=false",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    out: list[str] = []
    for raw in completed.stdout.split(b"\0"):
        if raw:
            try:
                out.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                continue
    return sorted(set(out))


@dataclass(slots=True)
class LoadedGraph:
    graph: CodeGraph
    path: Path
    freshness: Freshness
    built_commit: str | None

    def to_dict(self, repo_root: Path) -> dict[str, object]:
        try:
            rel = self.path.relative_to(repo_root).as_posix()
        except ValueError:
            rel = str(self.path)
        return {
            "path": rel,
            "built_commit": self.built_commit,
            **self.freshness.to_dict(),
        }


def load_code_graph(
    repo_root: Path,
    *,
    config: dict[str, object] | None = None,
    allow_stale: bool = False,
    ignore_stale: Iterable[str] = (),
    finalize: bool = True,
) -> LoadedGraph:
    """Load and index the symbol graph; raise ``GraphUnavailableError`` if missing or stale."""
    config = config if config is not None else load_config(repo_root)
    path = graph_file(repo_root, config)
    hint = rebuild_command(repo_root)
    if not path.is_file():
        raise GraphUnavailableError(
            "graph_missing",
            f"no symbol graph at {path}; build it with: {hint}",
            {"graph": str(path), "rebuild": hint},
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        graph = CodeGraph.from_symbol_graph(data)
    except (OSError, ValueError, TypeError) as exc:
        raise GraphUnavailableError(
            "graph_unreadable",
            f"symbol graph at {path} is unreadable ({exc}); rebuild it with: {hint}",
            {"graph": str(path), "rebuild": hint},
        ) from exc
    freshness = check_freshness(repo_root, config, path, ignore=ignore_stale)
    if freshness.stale and not allow_stale:
        sample = (freshness.changed + freshness.added + freshness.removed)[:5]
        count = len(freshness.changed) + len(freshness.added) + len(freshness.removed)
        raise GraphUnavailableError(
            "graph_stale",
            f"symbol graph is stale: {count} source file(s) differ from the build "
            f"(e.g. {', '.join(sample)}); rebuild it with: {hint} "
            "(or pass --allow-stale to use it anyway)",
            {"graph": str(path), "rebuild": hint, **freshness.to_dict()},
        )
    built_commit = None
    try:
        manifest = json.loads(
            (repo_root / MANIFEST_RELPATH).read_text(encoding="utf-8")
        )
        commit = manifest.get("repo", {}).get("last_commit")
        built_commit = str(commit) if commit and commit != "unknown" else None
    except (OSError, ValueError, AttributeError):
        pass
    if finalize:
        graph.finalize()
    return LoadedGraph(graph, path, freshness, built_commit)
