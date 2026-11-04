"""Python AST extractor: ``parse_python_file`` entry point plus ``PythonAstExtractor`` wrapper."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from akms.repo_wiki.errors import BuildError
from akms.repo_wiki.extract.base import Extractor
from akms.repo_wiki.models import Language, ParsedModule, SourceFile, SourceSpan, Symbol
from akms.repo_wiki.paths import module_name_from_path
from akms.repo_wiki.symbol_ids import build_symbol_id


def parse_python_file(source_file: SourceFile) -> ParsedModule:
    path = Path(source_file.abs_path)
    module = module_name_from_path(source_file.path)
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text, filename=source_file.path)
    except SyntaxError as exc:
        error = BuildError(
            path=source_file.path,
            stage="parse",
            message=exc.msg,
            line=exc.lineno,
            column=exc.offset,
        )
        return ParsedModule(source_file, module, None, [], [], [error])

    imports = extract_imports(tree)
    bindings = extract_import_bindings(
        tree, module, is_package=Path(source_file.path).name == "__init__.py"
    )
    tables = extract_dispatch_tables(tree, bindings)
    table_names = frozenset(tables) | frozenset(bindings)
    symbols: list[Symbol] = []
    seen: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.extend(
                parse_definition(
                    node,
                    source_file.path,
                    module,
                    None,
                    imports,
                    seen,
                    table_names=table_names,
                )
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            symbols.extend(
                parse_constant(node, source_file.path, module, imports, seen)
            )

    return ParsedModule(
        source_file,
        module,
        ast.get_docstring(tree),
        imports,
        symbols,
        [],
        bindings,
        dispatch_tables=tables,
        main_calls=extract_main_calls(
            tree, is_main_module=Path(source_file.path).name == "__main__.py"
        ),
    )


class PythonAstExtractor(Extractor):
    """Python AST backend; delegates to ``parse_python_file``."""

    language = Language.PYTHON

    def extract(self, source_file: SourceFile) -> ParsedModule:
        return parse_python_file(source_file)


def extract_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imports.extend(f"{module}.{alias.name}".strip(".") for alias in node.names)
    return sorted(dict.fromkeys(imports))


def extract_import_bindings(
    tree: ast.Module, module: str, *, is_package: bool
) -> dict[str, str]:
    """Module-scope names bound by imports, mapped to absolute dotted targets (``as`` honoured).

    Relative targets are resolved against the package; one that climbs above the root is dropped.
    """
    package = module.split(".") if is_package else module.split(".")[:-1]
    bindings: dict[str, str] = {}
    stack = list(tree.body)
    while stack:
        node = stack.pop(0)
        if isinstance(node, (ast.If, ast.Try)):
            stack.extend(node.body + node.orelse + getattr(node, "finalbody", []))
            for handler in getattr(node, "handlers", []):
                stack.extend(handler.body)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bindings[alias.asname] = alias.name
                else:
                    head = alias.name.split(".")[0]
                    bindings[head] = head
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 > len(package):
                    continue
                base = package[: len(package) - (node.level - 1)]
                source = ".".join([*base, *([node.module] if node.module else [])])
            else:
                source = node.module or ""
            for alias in node.names:
                if alias.name != "*" and source:
                    bindings[alias.asname or alias.name] = f"{source}.{alias.name}"
    return dict(sorted(bindings.items()))


def parse_definition(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    path: str,
    module: str,
    parent: Symbol | None,
    imports: list[str],
    seen: set[str],
    *,
    table_names: frozenset[str] = frozenset(),
) -> list[Symbol]:
    qualname = f"{parent.qualname}.{node.name}" if parent else node.name
    kind = (
        "class"
        if isinstance(node, ast.ClassDef)
        else ("method" if parent else "function")
    )
    start = node.lineno
    end = getattr(node, "end_lineno", node.lineno)
    symbol_id = unique_symbol_id(
        build_symbol_id(Language.PYTHON, path, qualname), start, seen
    )
    parent_id = parent.symbol_id if parent else None
    calls = extract_calls(node)
    is_class = isinstance(node, ast.ClassDef)
    symbol = Symbol(
        symbol_id=symbol_id,
        path=path,
        module=module,
        name=node.name,
        qualname=qualname,
        kind=kind,  # type: ignore[arg-type]
        parent_id=parent_id,
        start_line=start,
        end_line=end,
        signature=signature_for(node),
        docstring=ast.get_docstring(node),
        decorators=[safe_unparse(item) for item in getattr(node, "decorator_list", [])],
        bases=[safe_unparse(item) for item in getattr(node, "bases", [])],
        imports=imports,
        calls=calls,
        span=SourceSpan(path=path, start_line=start, end_line=end),
        language=Language.PYTHON,
        receivers={} if is_class else extract_receivers(node, calls),
        table_refs=[] if is_class else extract_table_refs(node, table_names),
        cli_handlers=[] if is_class else extract_cli_handlers(node),
    )
    result = [symbol]
    for child in node.body:
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            result.extend(
                parse_definition(
                    child,
                    path,
                    module,
                    symbol,
                    imports,
                    seen,
                    table_names=table_names,
                )
            )
    return result


def parse_constant(
    node: ast.Assign | ast.AnnAssign,
    path: str,
    module: str,
    imports: list[str],
    seen: set[str],
) -> list[Symbol]:
    names: list[str] = []
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                names.append(target.id)
    elif isinstance(node.target, ast.Name) and node.target.id.isupper():
        names.append(node.target.id)
    result: list[Symbol] = []
    for name in names:
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        result.append(
            Symbol(
                symbol_id=unique_symbol_id(
                    build_symbol_id(Language.PYTHON, path, name), start, seen
                ),
                path=path,
                module=module,
                name=name,
                qualname=name,
                kind="constant",
                parent_id=None,
                start_line=start,
                end_line=end,
                signature=None,
                docstring=None,
                decorators=[],
                bases=[],
                imports=imports,
                calls=[],
                span=SourceSpan(path=path, start_line=start, end_line=end),
                language=Language.PYTHON,
            )
        )
    return result


def signature_for(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(safe_unparse(base) for base in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = safe_unparse(node.args)
    returns = f" -> {safe_unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){returns}"


def extract_calls(node: ast.AST) -> list[str]:
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            calls.append(call_name(child.func))
    return sorted(dict.fromkeys(call for call in calls if call))


def _annotation_name(node: ast.AST | None) -> str:
    """The class an annotation names: ``C``, ``m.C``, ``"C"``, ``C | None``, ``Optional[C]``."""
    if node is None:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            node = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return ""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        sides = [
            side
            for side in (node.left, node.right)
            if not (isinstance(side, ast.Constant) and side.value is None)
        ]
        return _annotation_name(sides[0]) if len(sides) == 1 else ""
    if isinstance(node, ast.Subscript) and call_name(node.value) in (
        "Optional",
        "typing.Optional",
    ):
        return _annotation_name(node.slice)
    return call_name(node)


def extract_receivers(node: ast.AST, calls: list[str]) -> dict[str, list[str]]:
    """Local names bound by ``x = C(...)`` or ``x: C = ...`` and then used as ``x.m(...)``.

    Maps each such name to the sorted callable or annotation names it is bound to; whether
    a name is a class is decided later, against the graph. ``self`` and ``cls`` are left out
    (they are resolved through the enclosing class).
    """
    used = {
        call.split(".", 1)[0]
        for call in calls
        if "." in call and not call.startswith(("self.", "cls."))
    }
    if not used:
        return {}
    bound: dict[str, set[str]] = {}
    for child in ast.walk(node):
        if isinstance(child, ast.Assign) and isinstance(child.value, ast.Call):
            name = call_name(child.value.func)
            for target in child.targets:
                if name and isinstance(target, ast.Name) and target.id in used:
                    bound.setdefault(target.id, set()).add(name)
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            if child.target.id not in used:
                continue
            name = _annotation_name(child.annotation)
            if not name and isinstance(child.value, ast.Call):
                name = call_name(child.value.func)
            if name:
                bound.setdefault(child.target.id, set()).add(name)
    return {k: sorted(v) for k, v in sorted(bound.items())}


def extract_table_refs(node: ast.AST, names: frozenset[str]) -> list[str]:
    """Module-level *names* this definition indexes: ``NAME[key]`` or ``NAME.get(key)``."""
    if not names:
        return []
    found: set[str] = set()
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Subscript)
            and isinstance(child.value, ast.Name)
            and isinstance(child.ctx, ast.Load)
            and child.value.id in names
        ):
            found.add(child.value.id)
        elif (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "get"
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id in names
        ):
            found.add(child.func.value.id)
    return sorted(found)


def _is_main_guard(test: ast.expr) -> bool:
    """``__name__ == "__main__"`` (either way round)."""
    if not (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
    ):
        return False
    sides = [test.left, test.comparators[0]]
    names = [s for s in sides if isinstance(s, ast.Name) and s.id == "__name__"]
    consts = [s for s in sides if isinstance(s, ast.Constant) and s.value == "__main__"]
    return len(names) == 1 and len(consts) == 1


def extract_main_calls(tree: ast.Module, *, is_main_module: bool) -> list[str]:
    """Call names run when the module is executed as a script (sorted, unique).

    Those in a top-level ``if __name__ == "__main__":`` block; in ``__main__.py`` every
    module-level statement outside a definition counts.
    """
    statements: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            statements.extend(node.body)
        elif is_main_module and not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Import,
                ast.ImportFrom,
            ),
        ):
            statements.append(node)
    names: set[str] = set()
    for statement in statements:
        for child in ast.walk(statement):
            if isinstance(child, ast.Call):
                name = call_name(child.func)
                if name:
                    names.add(name)
    return sorted(names)


def extract_cli_handlers(node: ast.AST) -> list[str]:
    """Names registered as argparse command handlers: ``parser.set_defaults(func=f)``."""
    found: set[str] = set()
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "set_defaults"
        ):
            for keyword in child.keywords:
                if keyword.arg == "func" and isinstance(
                    keyword.value, (ast.Name, ast.Attribute)
                ):
                    name = call_name(keyword.value)
                    if name:
                        found.add(name)
    return sorted(found)


#: A dict literal needs at least this many entries to count as a dispatch table.
DISPATCH_TABLE_MIN_ENTRIES = 2


def extract_dispatch_tables(
    tree: ast.Module, bindings: dict[str, str]
) -> dict[str, list[str]]:
    """Module-level ``NAME = {literal: callable_name, ...}`` dicts: name -> sorted values.

    Every key must be a literal and every value a name (or dotted name) whose head is a
    function or class defined at module level or a name bound by an import. The shape is
    what counts; the table's name does not matter.
    """
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    known = defined | set(bindings)
    tables: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Dict):
            continue
        if len(value.keys) < DISPATCH_TABLE_MIN_ENTRIES:
            continue
        if not all(
            isinstance(key, ast.Constant) and key.value is not None
            for key in value.keys
        ):
            continue
        names = [
            call_name(item) if isinstance(item, (ast.Name, ast.Attribute)) else ""
            for item in value.values
        ]
        if all(name and name.split(".", 1)[0] in known for name in names):
            tables[target.id] = sorted(set(names))
    return dict(sorted(tables.items()))


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def unique_symbol_id(candidate: str, line: int, seen: set[str]) -> str:
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    suffixed = f"{candidate}@L{line}"
    seen.add(suffixed)
    return suffixed


def parsed_module_to_json(parsed: ParsedModule) -> str:
    return json.dumps(parsed.to_dict(), indent=2, sort_keys=True)
