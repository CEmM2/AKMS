"""Core data models for scanner, parser, renderer, and build state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal, cast

from akms.repo_wiki.errors import BuildError

SymbolKind = Literal["module", "class", "function", "method", "constant"]


class Language(Enum):
    """Source language (lowercase in manifests and IDs); older payloads default to PYTHON."""

    PYTHON = "python"
    RUST = "rust"
    CPP = "cpp"
    JULIA = "julia"


def _as_int(value: object) -> int:
    return int(cast(Any, value))


def _as_iter(value: object) -> Iterable[Any]:
    if value is None:
        return []
    return cast(Iterable[Any], value)


def _as_metadata(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in cast(dict[Any, Any], value).items()}


def _as_name_lists(value: object) -> dict[str, list[str]]:
    """``{name: [names]}`` from a JSON value; anything else reads as empty."""
    if not isinstance(value, dict):
        return {}
    return {
        str(k): [str(v) for v in _as_iter(items)]
        for k, items in cast(dict[Any, Any], value).items()
        if isinstance(items, list)
    }


@dataclass(slots=True)
class SourceFile:
    path: str
    abs_path: str
    language: str
    size_bytes: int
    content_hash: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SourceFile":
        return cls(
            path=str(data["path"]),
            abs_path=str(data["abs_path"]),
            language=str(data["language"]),
            size_bytes=_as_int(data["size_bytes"]),
            content_hash=str(data["content_hash"]),
        )


@dataclass(slots=True)
class SkippedFile:
    path: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SourceSpan:
    """1-indexed line range, inclusive at both ends; the IR carries spans, not source text."""

    path: str
    start_line: int
    end_line: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SourceSpan":
        return cls(
            path=str(data["path"]),
            start_line=_as_int(data["start_line"]),
            end_line=_as_int(data["end_line"]),
        )


@dataclass(slots=True)
class Symbol:
    symbol_id: str
    path: str
    module: str
    name: str
    qualname: str
    kind: SymbolKind
    parent_id: str | None
    start_line: int
    end_line: int
    signature: str | None
    docstring: str | None
    span: SourceSpan
    language: Language = Language.PYTHON  # older payloads lack a language
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    # Local name -> constructor/annotation names it is bound to, for names used as call
    # receivers (``x = Cls(); x.m()``). Python only; empty elsewhere.
    receivers: dict[str, list[str]] = field(default_factory=dict)
    # Module-level names this symbol indexes (``TABLE[key]``, ``TABLE.get(key)``) that may
    # be dispatch tables. Python only; empty elsewhere.
    table_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["language"] = self.language.value
        # Optional fields are left out when empty, so payloads without them stay unchanged.
        for key in ("metadata", "receivers", "table_refs"):
            if not d.get(key):
                d.pop(key, None)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Symbol":
        start_line = _as_int(data["start_line"])
        end_line = _as_int(data["end_line"])
        path = str(data["path"])
        span_raw = data.get("span")
        if span_raw is None:
            # Older payloads lack a span: synthesize it from path/start_line/end_line.
            span = SourceSpan(path=path, start_line=start_line, end_line=end_line)
        else:
            span = SourceSpan.from_dict(cast(dict[str, object], span_raw))
        # Older payloads lack a language: default to PYTHON.
        lang_raw = data.get("language")
        language = Language(str(lang_raw)) if lang_raw is not None else Language.PYTHON
        return cls(
            symbol_id=str(data["symbol_id"]),
            path=path,
            module=str(data["module"]),
            name=str(data["name"]),
            qualname=str(data["qualname"]),
            kind=cast(SymbolKind, data["kind"]),
            parent_id=str(data["parent_id"]) if data.get("parent_id") else None,
            start_line=start_line,
            end_line=end_line,
            signature=str(data["signature"]) if data.get("signature") else None,
            docstring=str(data["docstring"]) if data.get("docstring") else None,
            span=span,
            language=language,
            decorators=[str(v) for v in _as_iter(data.get("decorators"))],
            bases=[str(v) for v in _as_iter(data.get("bases"))],
            imports=[str(v) for v in _as_iter(data.get("imports"))],
            calls=[str(v) for v in _as_iter(data.get("calls"))],
            metadata=_as_metadata(data.get("metadata")),
            receivers=_as_name_lists(data.get("receivers")),
            table_refs=[str(v) for v in _as_iter(data.get("table_refs"))],
        )


@dataclass(slots=True)
class ParsedModule:
    source_file: SourceFile
    module: str
    docstring: str | None
    imports: list[str]
    symbols: list[Symbol]
    errors: list[BuildError] = field(default_factory=list)
    # Local name -> absolute dotted import target, at module scope (Python only).
    import_bindings: dict[str, str] = field(default_factory=dict)
    # Module-level dict literals whose values are all module-level or imported names:
    # table name -> sorted value names (Python only).
    dispatch_tables: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "source_file": self.source_file.to_dict(),
            "module": self.module,
            "docstring": self.docstring,
            "imports": self.imports,
            "import_bindings": dict(self.import_bindings),
            "symbols": [symbol.to_dict() for symbol in self.symbols],
            "errors": [error.to_dict() for error in self.errors],
        }
        if self.dispatch_tables:
            data["dispatch_tables"] = {
                k: list(v) for k, v in sorted(self.dispatch_tables.items())
            }
        return data

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
        *,
        repo_root: Path | str | None = None,
    ) -> "ParsedModule":
        """Deserialize; *repo_root* rehydrates ``abs_path`` so cached IR is machine-independent."""
        source_raw = cast(dict[str, object], data["source_file"])
        source = SourceFile.from_dict(source_raw)
        if repo_root is not None:
            root = Path(repo_root)
            source = SourceFile(
                path=source.path,
                abs_path=str((root / source.path).resolve()),
                language=source.language,
                size_bytes=source.size_bytes,
                content_hash=source.content_hash,
            )
        symbols = [
            Symbol.from_dict(cast(dict[str, object], item))
            for item in _as_iter(data.get("symbols"))
        ]
        errors = [
            BuildError.from_dict(cast(dict[str, object], item))
            for item in _as_iter(data.get("errors"))
        ]
        docstring = data.get("docstring")
        bindings = data.get("import_bindings")
        return cls(
            source_file=source,
            module=str(data["module"]),
            docstring=str(docstring) if docstring is not None else None,
            imports=[str(v) for v in _as_iter(data.get("imports"))],
            symbols=symbols,
            errors=errors,
            import_bindings=(
                {str(k): str(v) for k, v in bindings.items()}
                if isinstance(bindings, dict)
                else {}
            ),
            dispatch_tables=_as_name_lists(data.get("dispatch_tables")),
        )


@dataclass(slots=True)
class ManifestFile:
    language: str
    hash: str
    module_doc: str | None = None
    symbols: dict[str, dict[str, object]] = field(default_factory=dict)
    summary_hash: str | None = None
    index_hash: str | None = None


@dataclass(slots=True)
class Manifest:
    repo: dict[str, object]
    files: dict[str, ManifestFile] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "repo": self.repo,
            "files": {
                path: {
                    "language": file.language,
                    "hash": file.hash,
                    "module_doc": file.module_doc,
                    "symbols": file.symbols,
                    "summary_hash": file.summary_hash,
                    "index_hash": file.index_hash,
                }
                for path, file in sorted(self.files.items())
            },
        }


@dataclass(slots=True)
class BuildSummary:
    """Counters for one run; ``parsed`` counts fresh extractions only, not cache hits."""

    scanned: int = 0
    parsed: int = 0  # fresh extract successes only (not cache hits)
    generated_module_docs: int = 0
    generated_symbol_docs: int = 0
    generated_summaries: int = 0
    skipped: int = 0
    errors: list[BuildError] = field(default_factory=list)
    backend_notes: list[str] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    cache_writes: int = 0
    cache_invalidations: int = 0
    cache_corruptions: int = 0
    cache_removals: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "scanned": self.scanned,
            "parsed": self.parsed,
            "generated_module_docs": self.generated_module_docs,
            "generated_symbol_docs": self.generated_symbol_docs,
            "generated_summaries": self.generated_summaries,
            "skipped": self.skipped,
            "errors": [error.to_dict() for error in self.errors],
            "backend_notes": self.backend_notes,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_writes": self.cache_writes,
            "cache_invalidations": self.cache_invalidations,
            "cache_corruptions": self.cache_corruptions,
            "cache_removals": self.cache_removals,
        }
