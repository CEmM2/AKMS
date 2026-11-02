"""Tree-sitter per-file extractors for Rust, C++ and Julia (optional extras).

When ``tree_sitter`` or a grammar wheel is missing the subclass raises at construction and the
registry records a note.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from akms.repo_wiki.errors import BuildError
from akms.repo_wiki.extract.base import Extractor
from akms.repo_wiki.models import Language, ParsedModule, SourceSpan, Symbol
from akms.repo_wiki.paths import module_name_from_path
from akms.repo_wiki.symbol_ids import build_symbol_id

if TYPE_CHECKING:
    from tree_sitter import Node
    from akms.repo_wiki.models import SourceFile, SymbolKind


class _Frame:
    """Scope-stack entry; ``is_type`` scopes (class/struct/trait/``impl``) make methods."""

    __slots__ = ("segment", "parent", "is_type")

    def __init__(
        self, segment: str | None, parent: Symbol | None, is_type: bool
    ) -> None:
        self.segment = segment
        self.parent = parent
        self.is_type = is_type


class TreeSitterExtractor(Extractor):
    """Generic tree-sitter walker; subclasses supply grammar, joiner and node-type tables."""

    language: Language
    extensions: tuple[str, ...] = ()
    joiner: str = "::"
    symbol_nodes: dict[str, str] = {}
    scope_nodes: frozenset[str] = frozenset()
    comment_nodes: frozenset[str] = frozenset()

    def __init__(self) -> None:
        # Imported lazily so the default (zero-dep) install never needs tree-sitter.
        from tree_sitter import Language as TSLanguage
        from tree_sitter import Parser

        self._parser = Parser(TSLanguage(self._grammar()))

    @staticmethod
    def _grammar() -> object:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    def extract(self, source_file: "SourceFile") -> ParsedModule:
        path = source_file.path
        module = module_name_from_path(path)
        try:
            source = Path(source_file.abs_path).read_bytes()
        except OSError as exc:
            error = BuildError(path=path, stage="read", message=str(exc))
            return ParsedModule(source_file, module, None, [], [], [error])

        tree = self._parser.parse(source)
        symbols: list[Symbol] = []
        seen: set[str] = set()
        self._walk(tree.root_node, source, path, module, [], symbols, seen)

        errors: list[BuildError] = []
        if tree.root_node.has_error:
            errors.append(
                BuildError(
                    path=path,
                    stage="parse",
                    message="tree-sitter reported syntax errors",
                )
            )
        return ParsedModule(source_file, module, None, [], symbols, errors)

    def _walk(
        self,
        node: "Node",
        source: bytes,
        path: str,
        module: str,
        stack: list[_Frame],
        out: list[Symbol],
        seen: set[str],
    ) -> None:
        kind_hint = self.symbol_nodes.get(node.type)
        if kind_hint is not None:
            name = self._name_of(node)
            if name:
                symbol = self._make_symbol(
                    node, source, path, module, name, kind_hint, stack, seen
                )
                out.append(symbol)
                if kind_hint in ("class", "module"):
                    stack.append(_Frame(name, symbol, is_type=kind_hint == "class"))
                    self._walk_children(node, source, path, module, stack, out, seen)
                    stack.pop()
                    return
                self._walk_children(node, source, path, module, stack, out, seen)
                return

        if node.type in self.scope_nodes:
            seg = self._name_of(node)
            stack.append(_Frame(seg, None, is_type=True))
            self._walk_children(node, source, path, module, stack, out, seen)
            stack.pop()
            return

        self._walk_children(node, source, path, module, stack, out, seen)

    def _walk_children(self, node, source, path, module, stack, out, seen) -> None:
        for child in node.children:
            self._walk(child, source, path, module, stack, out, seen)

    def _make_symbol(
        self,
        node: "Node",
        source: bytes,
        path: str,
        module: str,
        name: str,
        kind_hint: str,
        stack: list[_Frame],
        seen: set[str],
    ) -> Symbol:
        segments = [f.segment for f in stack if f.segment]
        qualname = self.joiner.join([*segments, name]) if segments else name
        kind: "SymbolKind"
        if kind_hint == "function":
            kind = "method" if any(f.is_type for f in stack) else "function"
        else:
            kind = kind_hint  # type: ignore[assignment]
        parent = next((f.parent for f in reversed(stack) if f.parent is not None), None)
        start = node.start_point[0] + 1
        end = node.end_point[0] + 1
        symbol_id = _unique(build_symbol_id(self.language, path, qualname), start, seen)
        calls = self._call_names(node) if kind_hint == "function" else []
        return Symbol(
            symbol_id=symbol_id,
            path=path,
            module=module,
            name=name,
            qualname=qualname,
            kind=kind,
            parent_id=parent.symbol_id if parent else None,
            start_line=start,
            end_line=end,
            signature=self._signature(node, source),
            docstring=self._leading_doc(node, source),
            span=SourceSpan(path=path, start_line=start, end_line=end),
            language=self.language,
            calls=sorted(dict.fromkeys(c for c in calls if c)),
        )

    def _name_of(self, node: "Node") -> str | None:
        """Default: the node's ``name`` field, else its first ``identifier`` child."""
        named = node.child_by_field_name("name")
        if named is not None:
            return _text(named)
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return _text(child)
        return None

    def _call_names(self, node: "Node") -> list[str]:
        """Default heuristic: every ``call_expression`` callee within the subtree."""
        names: list[str] = []
        stack = list(node.children)
        while stack:
            cur = stack.pop()
            if cur.type == "call_expression":
                callee = cur.child_by_field_name("function") or (
                    cur.children[0] if cur.children else None
                )
                if callee is not None:
                    names.append(self._callee_text(callee))
            stack.extend(cur.children)
        return names

    @staticmethod
    def _callee_text(callee: "Node") -> str:
        """Reduce a callee node to a recordable name (last field on member access)."""
        if callee.type in ("field_expression", "field_access"):
            field = callee.child_by_field_name("field")
            if field is not None:
                return _text(field)
            for child in reversed(callee.children):
                if child.type in ("field_identifier", "identifier"):
                    return _text(child)
        return _text(callee).split("(")[0].strip()

    def _signature(self, node: "Node", source: bytes) -> str | None:
        """First non-empty line of the node text (scans bytes; avoids decoding large bodies)."""
        start, end = node.start_byte, node.end_byte
        while start < end:
            next_nl = source.find(b"\n", start, end)
            line_end = next_nl if next_nl != -1 else end
            line_bytes = source[start:line_end].strip()
            if line_bytes:
                line_text = line_bytes.decode(errors="replace")
                return line_text.rstrip("{").strip() or line_text
            if next_nl == -1:
                break
            start = next_nl + 1
        return None

    def _leading_doc(self, node: "Node", source: bytes) -> str | None:
        """Collect contiguous comment siblings immediately above *node*."""
        if not self.comment_nodes:
            return None
        comments: list[str] = []
        sib = node.prev_sibling
        while sib is not None and sib.type in self.comment_nodes:
            comments.append(_text(sib))
            sib = sib.prev_sibling
        if not comments:
            return None
        comments.reverse()
        cleaned = [_strip_comment(c) for c in comments]
        joined = "\n".join(line for line in cleaned if line is not None)
        return joined.strip() or None


def _text(node: "Node") -> str:
    """Decode a node's source text, tolerating the grammar stubs' ``bytes | None``."""
    return node.text.decode() if node.text is not None else ""


def _unique(candidate: str, line: int, seen: set[str]) -> str:
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    suffixed = f"{candidate}@L{line}"
    seen.add(suffixed)
    return suffixed


def _strip_comment(raw: str) -> str:
    text = raw.strip()
    for prefix in ("///", "//!", "//", "#"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    if text.startswith("/*"):
        return text[2:].rstrip("*/").strip()
    return text


class RustExtractor(TreeSitterExtractor):
    """Rust per-file extractor (``::`` qualnames)."""

    language = Language.RUST
    extensions = (".rs",)
    joiner = "::"
    symbol_nodes = {
        "struct_item": "class",
        "enum_item": "class",
        "trait_item": "class",
        "function_item": "function",
        "function_signature_item": "function",
    }
    scope_nodes = frozenset({"impl_item"})
    comment_nodes = frozenset({"line_comment", "block_comment"})

    @staticmethod
    def _grammar() -> object:
        import tree_sitter_rust

        return tree_sitter_rust.language()

    def _name_of(self, node: "Node") -> str | None:
        for child in node.children:
            if child.type in ("type_identifier", "identifier"):
                return _text(child)
        return None


class CppExtractor(TreeSitterExtractor):
    """C++ extractor (``::`` qualnames); namespaces are transparent (``Type::method``)."""

    language = Language.CPP
    extensions = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h", ".hxx")
    joiner = "::"
    symbol_nodes = {
        "struct_specifier": "class",
        "class_specifier": "class",
        "function_definition": "function",
    }
    scope_nodes = frozenset()
    comment_nodes = frozenset({"comment"})

    @staticmethod
    def _grammar() -> object:
        import tree_sitter_cpp

        return tree_sitter_cpp.language()

    def _name_of(self, node: "Node") -> str | None:
        if node.type in ("struct_specifier", "class_specifier"):
            ident = node.child_by_field_name("name")
            if ident is not None:
                return _text(ident)
            for child in node.children:
                if child.type == "type_identifier":
                    return _text(child)
            return None
        # function_definition → descend the declarator to the (field_)identifier.
        declarator = node.child_by_field_name("declarator")
        return _cpp_declarator_name(declarator) if declarator is not None else None


def _cpp_declarator_name(node: "Node | None") -> str | None:
    while node is not None:
        if node.type in ("identifier", "field_identifier"):
            return _text(node)
        if node.type == "qualified_identifier":
            for child in reversed(node.children):
                if child.type in ("identifier", "field_identifier"):
                    return _text(child)
            return _text(node)
        node = node.child_by_field_name("declarator") or (
            node.children[0] if node.children else None
        )
    return None


class JuliaExtractor(TreeSitterExtractor):
    """Julia per-file extractor (``.`` qualnames)."""

    language = Language.JULIA
    extensions = (".jl",)
    joiner = "."
    symbol_nodes = {
        "module_definition": "module",
        "struct_definition": "class",
        "function_definition": "function",
        "assignment": "function",
    }
    scope_nodes = frozenset()
    comment_nodes = frozenset({"line_comment", "comment"})

    @staticmethod
    def _grammar() -> object:
        import tree_sitter_julia

        return tree_sitter_julia.language()

    def _name_of(self, node: "Node") -> str | None:
        if node.type == "module_definition":
            for child in node.children:
                if child.type == "identifier":
                    return _text(child)
            return None
        if node.type == "struct_definition":
            head = node.child_by_field_name("name")
            target = head or next(
                (c for c in node.children if c.type == "type_head"), None
            )
            if target is not None:
                ident = next(
                    (c for c in target.children if c.type == "identifier"), target
                )
                return _text(ident)
            return None
        # function_definition / short-form assignment: the name is the callee of the defining call.
        call = _first_descendant(node, "call_expression")
        if call is not None:
            ident = next((c for c in call.children if c.type == "identifier"), None)
            if ident is not None:
                return _text(ident)
        return None

    def _make_short_form(self, node: "Node") -> bool:
        return (
            node.type == "assignment"
            and _first_descendant(node, "call_expression") is not None
        )

    def _walk(self, node, source, path, module, stack, out, seen) -> None:  # type: ignore[override]
        # Treat ``assignment`` as a symbol only when its LHS is a call (``f() = ...``).
        if node.type == "assignment" and not self._make_short_form(node):
            self._walk_children(node, source, path, module, stack, out, seen)
            return
        super()._walk(node, source, path, module, stack, out, seen)

    def _call_names(self, node: "Node") -> list[str]:
        # Skip the definition's own signature so the function name is not counted as a call.
        names: list[str] = []
        defining = _first_descendant(node, "call_expression")
        stack = list(node.children)
        while stack:
            cur = stack.pop()
            if cur.type == "call_expression" and cur is not defining:
                ident = next((c for c in cur.children if c.type == "identifier"), None)
                if ident is not None:
                    names.append(_text(ident))
            stack.extend(cur.children)
        return names


def _first_descendant(node: "Node", node_type: str) -> "Node | None":
    queue: deque["Node"] = deque(node.children)
    while queue:
        cur = queue.popleft()
        if cur.type == node_type:
            return cur
        queue.extend(cur.children)
    return None
