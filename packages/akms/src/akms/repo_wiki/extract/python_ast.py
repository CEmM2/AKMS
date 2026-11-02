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
    symbols: list[Symbol] = []
    seen: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.extend(
                parse_definition(node, source_file.path, module, None, imports, seen)
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            symbols.extend(
                parse_constant(node, source_file.path, module, imports, seen)
            )

    return ParsedModule(
        source_file, module, ast.get_docstring(tree), imports, symbols, [], bindings
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
        calls=extract_calls(node),
        span=SourceSpan(path=path, start_line=start, end_line=end),
        language=Language.PYTHON,
    )
    result = [symbol]
    for child in node.body:
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            result.extend(parse_definition(child, path, module, symbol, imports, seen))
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
