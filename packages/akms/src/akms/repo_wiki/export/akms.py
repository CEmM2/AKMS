"""Public, dependency-free contract for exporting repository-wiki mirrors to AKMS."""

from __future__ import annotations

import html
import json
import os
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final, Mapping

from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.models import Language, ParsedModule, Symbol

EXPORT_SCHEMA_VERSION: Final = 1
"""Version of the repo-wiki-to-AKMS export and command-result schema."""

AKMS_SCHEMA_VERSION: Final = "v2"
"""Frozen AKMS frontmatter schema consumed by the export."""

CODE_MIRROR_FRONTMATTER_FIELDS: Final = (
    "id",
    "title",
    "domain",
    "status",
    "confidence",
    "source",
    "auto_update",
    "content_ref",
    "source_file",
    "generated_at",
    "generated_by_phase",
    "akms_schema",
)
"""Exact fields accepted by AKMS v2 ``CodeMirrorNodeFrontmatter``."""

MIRROR_SUMMARY_MAX_CHARS: Final = 800
"""Cap on a mirror's ``## Summary``, the 200 tokens routing mode charges per node."""

_BLANK_LINE: Final = re.compile(r"\n\s*\n")
_SUMMARY_DOCSTRING_MAX_CHARS: Final = 300
_SUMMARY_MAX_METHODS: Final = 5
_SUMMARY_SIGNATURE_MAX_CHARS: Final = 120
_SUMMARY_CLASS_MAX_CHARS: Final = 200

_SUPPORTED_LANGUAGES: Final = frozenset(language.value for language in Language)


def _language_value(language: Language | str) -> str:
    value = language.value if isinstance(language, Language) else str(language)
    if value not in _SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(_SUPPORTED_LANGUAGES))
        raise ValueError(
            f"Unsupported AKMS mirror language {value!r}; expected one of: {supported}"
        )
    return value


def normalize_source_path(source_path: str) -> str:
    """Return a canonical repository-relative POSIX path; absolute and ``..`` paths are rejected.

    Windows drive/UNC forms are rejected via ``PureWindowsPath`` even on POSIX hosts.
    """

    normalized = source_path.replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        raise ValueError("source_path must name a repository-relative file")
    # Reject Windows drive/root/UNC forms even on POSIX, where "C:/..." looks relative.
    windows_path = PureWindowsPath(normalized)
    if windows_path.drive or windows_path.root:
        raise ValueError(
            f"source_path must not be absolute or traverse parents: {source_path!r}"
        )
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"source_path must not be absolute or traverse parents: {source_path!r}"
        )
    canonical = path.as_posix()
    if canonical in {"", "."}:
        raise ValueError("source_path must name a repository-relative file")
    return canonical


def canonical_generated_at(generated_at: datetime | str) -> str:
    """Validate and canonicalize an explicit ISO-8601 export timestamp."""

    if isinstance(generated_at, datetime):
        return generated_at.isoformat()
    if not generated_at:
        raise ValueError("generated_at must be an explicit ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(generated_at)
    except ValueError as exc:
        raise ValueError(
            f"generated_at is not a valid ISO-8601 timestamp: {generated_at!r}"
        ) from exc
    return parsed.isoformat()


def resolve_generated_at(
    generated_at: datetime | str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return ``generated_at`` or ``SOURCE_DATE_EPOCH`` (no wall clock); neither is an error."""

    if generated_at is not None and generated_at != "":
        return canonical_generated_at(generated_at)
    env = os.environ if environ is None else environ
    epoch_raw = env.get("SOURCE_DATE_EPOCH")
    if epoch_raw is None or epoch_raw == "":
        raise ValueError(
            "deterministic export requires --generated-at or SOURCE_DATE_EPOCH"
        )
    try:
        epoch = int(epoch_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"SOURCE_DATE_EPOCH must be an integer unix timestamp, got {epoch_raw!r}"
        ) from exc
    if epoch < 0:
        raise ValueError(f"SOURCE_DATE_EPOCH must be non-negative, got {epoch}")
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def _validate_phase(phase: int) -> int:
    if isinstance(phase, bool) or phase < 1:
        raise ValueError(f"phase must be a positive integer, got {phase!r}")
    return phase


def _encode_non_python_id_path(source_path: str) -> str:
    """Injectively encode a UTF-8 path using AKMS-friendly ID characters."""

    encoded: list[str] = []
    for byte in source_path.encode("utf-8"):
        char = chr(byte)
        if char.isascii() and (char.islower() or char.isdigit() or char == "-"):
            encoded.append(char)
        else:
            encoded.append(f"_{byte:02x}")
    return "".join(encoded)


def mirror_node_id(source_path: str, language: Language | str) -> str:
    """Build the stable AKMS node ID (Python: legacy algorithm; others: injective encoding)."""

    path = normalize_source_path(source_path)
    language_value = _language_value(language)
    if language_value == Language.PYTHON.value:
        return "mirror-" + path.replace("/", "-").replace(".py", "").replace(".", "-")
    return f"mirror-{language_value}-{_encode_non_python_id_path(path)}"


def mirror_content_ref(source_path: str, language: Language | str) -> str:
    """Build the AKMS-relative ``content_ref`` for a generated document."""

    path = normalize_source_path(source_path)
    language_value = _language_value(language)
    if language_value == Language.PYTHON.value:
        return f"code-mirror/{path.replace('.py', '.md')}"
    return f"code-mirror/{language_value}/{path}.md"


KNOWLEDGE_DIRS: Final = ("knowledge", ".knowledge")
"""Knowledge directory names a mirror may be written under, relative to the output root."""

DEFAULT_KNOWLEDGE_DIR: Final = ".knowledge"


def validate_knowledge_dir(knowledge_dir: str) -> str:
    """Return ``knowledge_dir`` if it is one of :data:`KNOWLEDGE_DIRS`."""

    if knowledge_dir not in KNOWLEDGE_DIRS:
        raise ValueError(
            f"knowledge_dir must be one of {', '.join(KNOWLEDGE_DIRS)}; "
            f"got {knowledge_dir!r}"
        )
    return knowledge_dir


def mirror_document_path(
    source_path: str,
    language: Language | str,
    knowledge_dir: str = DEFAULT_KNOWLEDGE_DIR,
) -> str:
    """Build the output-relative generated path, distinct from source path.

    ``content_ref`` is relative to the knowledge directory, so it does not
    depend on ``knowledge_dir``; only the generated path does.
    """

    return f"{validate_knowledge_dir(knowledge_dir)}/{mirror_content_ref(source_path, language)}"


@dataclass(frozen=True, slots=True)
class MirrorDocument:
    """Complete deterministic producer contract for one source-file mirror."""

    source_path: str
    language: str
    source_hash: str
    phase: int
    generated_at: str
    node_id: str
    content_ref: str
    generated_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_mirror_document(
    *,
    source_path: str,
    language: Language | str,
    source_hash: str,
    phase: int,
    generated_at: datetime | str,
    knowledge_dir: str = DEFAULT_KNOWLEDGE_DIR,
) -> MirrorDocument:
    """Create a mirror contract record without reading or writing the filesystem."""

    path = normalize_source_path(source_path)
    language_value = _language_value(language)
    if not source_hash:
        raise ValueError("source_hash must be explicit and non-empty")
    return MirrorDocument(
        source_path=path,
        language=language_value,
        source_hash=source_hash,
        phase=_validate_phase(phase),
        generated_at=canonical_generated_at(generated_at),
        node_id=mirror_node_id(path, language_value),
        content_ref=mirror_content_ref(path, language_value),
        generated_path=mirror_document_path(path, language_value, knowledge_dir),
    )


@dataclass(frozen=True, slots=True)
class WrittenRecord:
    """A mirror document atomically written by an export command."""

    source_path: str
    language: str
    source_hash: str
    node_id: str
    content_ref: str
    generated_path: str

    @classmethod
    def from_document(cls, document: MirrorDocument) -> WrittenRecord:
        return cls(
            source_path=document.source_path,
            language=document.language,
            source_hash=document.source_hash,
            node_id=document.node_id,
            content_ref=document.content_ref,
            generated_path=document.generated_path,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RemovedRecord:
    """A stale generated document removed after a completely successful export."""

    source_path: str
    language: str
    node_id: str
    content_ref: str
    generated_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SkippedRecord:
    """A source intentionally not exported, with a machine-readable reason."""

    source_path: str
    language: str
    source_hash: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    """A source-scoped export failure suitable for JSON reporting."""

    source_path: str | None
    language: str | None
    stage: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SelectedRecord:
    """A source path selected for this export, with its content hash."""

    source_path: str
    language: str
    source_hash: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _record_sort_key(record: object) -> tuple[str, ...]:
    data = asdict(record)  # type: ignore[arg-type]
    return tuple(
        "" if value is None else str(value) for _, value in sorted(data.items())
    )


@dataclass(slots=True)
class ExportResult:
    """Stable command result with explicit context and per-outcome records."""

    phase: int
    generated_at: datetime | str
    written: list[WrittenRecord] = field(default_factory=list)
    removed: list[RemovedRecord] = field(default_factory=list)
    skipped: list[SkippedRecord] = field(default_factory=list)
    errors: list[ErrorRecord] = field(default_factory=list)
    selected: list[SelectedRecord] = field(default_factory=list)
    selection: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-ready mapping."""

        selection = dict(self.selection)
        return {
            "export_schema_version": EXPORT_SCHEMA_VERSION,
            "phase": _validate_phase(self.phase),
            "generated_at": canonical_generated_at(self.generated_at),
            "selection": selection,
            "selected": [
                record.to_dict()
                for record in sorted(self.selected, key=_record_sort_key)
            ],
            "written": [
                record.to_dict()
                for record in sorted(self.written, key=_record_sort_key)
            ],
            "removed": [
                record.to_dict()
                for record in sorted(self.removed, key=_record_sort_key)
            ],
            "skipped": [
                record.to_dict()
                for record in sorted(self.skipped, key=_record_sort_key)
            ],
            "errors": [
                record.to_dict() for record in sorted(self.errors, key=_record_sort_key)
            ],
        }

    def to_json(self) -> str:
        """Serialize the command result to byte-deterministic compact JSON."""

        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


def _validated_document(parsed: ParsedModule, document: MirrorDocument) -> None:
    """Reject a document whose identity or source metadata does not match its parsed module."""

    # The knowledge directory is the generated path's first segment; any other
    # value cannot rebuild the same path, so the comparison below rejects it.
    knowledge_dir = document.generated_path.split("/", 1)[0]
    expected = build_mirror_document(
        source_path=document.source_path,
        language=document.language,
        source_hash=document.source_hash,
        phase=document.phase,
        generated_at=document.generated_at,
        knowledge_dir=(
            knowledge_dir if knowledge_dir in KNOWLEDGE_DIRS else DEFAULT_KNOWLEDGE_DIR
        ),
    )
    if document != expected:
        raise ValueError(
            "MirrorDocument identity fields are inconsistent with the export contract"
        )

    source = parsed.source_file
    if normalize_source_path(source.path) != document.source_path:
        raise ValueError(
            f"ParsedModule source path {source.path!r} does not match {document.source_path!r}"
        )
    if _language_value(source.language) != document.language:
        raise ValueError(
            f"ParsedModule language {source.language!r} does not match {document.language!r}"
        )
    if source.content_hash != document.source_hash:
        raise ValueError(
            "ParsedModule source hash does not match MirrorDocument source_hash"
        )

    for symbol in parsed.symbols:
        if normalize_source_path(symbol.path) != document.source_path:
            raise ValueError(
                f"Symbol {symbol.symbol_id!r} belongs to {symbol.path!r}, "
                f"not {document.source_path!r}"
            )
        if symbol.language.value != document.language:
            raise ValueError(
                f"Symbol {symbol.symbol_id!r} language {symbol.language.value!r} "
                f"does not match {document.language!r}"
            )


def _frontmatter(document: MirrorDocument) -> dict[str, object]:
    """Build only the frozen AKMS v2 code-mirror fields."""

    return {
        "id": document.node_id,
        "title": f"Code Mirror: {document.source_path}",
        "domain": "code-mirror",
        "status": "established",
        "confidence": 1.0,
        "source": "generated",
        "auto_update": True,
        "content_ref": document.content_ref,
        "source_file": document.source_path,
        "generated_at": document.generated_at,
        "generated_by_phase": document.phase,
        "akms_schema": AKMS_SCHEMA_VERSION,
    }


def _dump_frontmatter(document: MirrorDocument) -> str:
    """Serialize frozen scalar frontmatter as JSON-compatible YAML."""

    return "".join(
        f"{key}: {json.dumps(value, ensure_ascii=True, allow_nan=False)}\n"
        for key, value in sorted(_frontmatter(document).items())
    )


def _markdown_path(source_path: str) -> str:
    """Render a path as safe inline HTML with control characters made visible."""

    visible = json.dumps(source_path, ensure_ascii=True)[1:-1]
    return f"<code>{html.escape(visible)}</code>"


def _symbol_metadata(symbol: Symbol) -> dict[str, object]:
    """Project searchable symbol fields without copying source text."""

    return {
        "symbol_id": symbol.symbol_id,
        "kind": symbol.kind,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "signature": symbol.signature,
        "docstring": symbol.docstring,
        "calls": symbol.calls,
        "bases": symbol.bases,
        "parent_id": symbol.parent_id,
    }


def _markdown_fence(text: str) -> str:
    """Return a backtick fence longer than every run present in ``text``."""

    longest = 0
    current = 0
    for character in text:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return "`" * max(3, longest + 1)


def _one_line(text: str) -> str:
    """Collapse all whitespace, so summary text can never start a section or fence."""

    return " ".join(text.split())


def _capped(text: str, limit: int) -> str:
    """Cut ``text`` at a word boundary to at most ``limit`` characters."""

    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "..."


def _is_public(symbol: Symbol) -> bool:
    return not symbol.name.startswith("_")


def _short_signature(symbol: Symbol) -> str:
    """Return a symbol's capped one-line signature, without ``def``/``class`` keywords."""

    signature = _one_line(symbol.signature or "") or symbol.name
    for keyword in ("async def ", "def ", "class ", "fn ", "function ", "struct "):
        if signature.startswith(keyword):
            signature = signature[len(keyword) :]
            break
    return _capped(signature, _SUMMARY_SIGNATURE_MAX_CHARS)


def _summary_class(symbol: Symbol, symbols: list[Symbol]) -> str:
    """Render a class as its signature and the first few public method names."""

    methods = [
        child.name
        for child in symbols
        if child.parent_id == symbol.symbol_id
        and child.kind == "method"
        and _is_public(child)
    ]
    item = f"`{_short_signature(symbol)}`"
    if not methods:
        return item
    shown = ", ".join(methods[:_SUMMARY_MAX_METHODS])
    hidden = len(methods) - _SUMMARY_MAX_METHODS
    more = f", +{hidden} more" if hidden > 0 else ""
    return _capped(f"{item} ({shown}{more})", _SUMMARY_CLASS_MAX_CHARS)


def _fit_items(items: list[str], budget: int) -> tuple[list[str], int]:
    """Keep the leading items that fit ``budget`` characters, always naming the rest."""

    kept: list[str] = []
    used = 0
    for index, item in enumerate(items):
        cost = len(item) + 2
        remaining = len(items) - index - 1
        reserve = len(f"+{remaining} more") + 2 if remaining else 0
        if used + cost + reserve > budget:
            break
        kept.append(item)
        used += cost
    hidden = len(items) - len(kept)
    if hidden:
        kept.append(f"+{hidden} more")
    return kept, used


def render_mirror_summary(parsed: ParsedModule) -> str:
    """Render a mirror's ``## Summary`` body from facts the extractor already holds.

    It is a pure function of one file's parse: the first paragraph of the module
    docstring and the public top-level classes and functions with their
    signatures, in source order. Deterministic, at most
    ``MIRROR_SUMMARY_MAX_CHARS`` characters, and never empty.
    """

    symbols = sorted(
        parsed.symbols,
        key=lambda item: (item.start_line, item.end_line, item.symbol_id),
    )
    modules = {item.symbol_id for item in symbols if item.kind == "module"}
    top_level = [
        item
        for item in symbols
        if _is_public(item) and (item.parent_id is None or item.parent_id in modules)
    ]
    classes = [
        _summary_class(item, symbols) for item in top_level if item.kind == "class"
    ]
    functions = [
        f"`{_short_signature(item)}`" for item in top_level if item.kind == "function"
    ]

    paragraphs: list[str] = []
    first_paragraph = _BLANK_LINE.split((parsed.docstring or "").strip(), maxsplit=1)[0]
    docstring = _one_line(first_paragraph).lstrip("# ")
    if docstring:
        paragraphs.append(_capped(docstring, _SUMMARY_DOCSTRING_MAX_CHARS))

    labels = len("Classes: ") + len("Functions: ") + 8
    budget = MIRROR_SUMMARY_MAX_CHARS - labels - sum(len(p) for p in paragraphs)
    # Classes may take half the room when there are functions too; what they
    # leave goes to the functions.
    kept_classes, used = _fit_items(classes, budget // 2 if functions else budget)
    kept_functions, _ = _fit_items(functions, budget - used)
    if kept_classes:
        paragraphs.append("Classes: " + ", ".join(kept_classes))
    if kept_functions:
        paragraphs.append("Functions: " + ", ".join(kept_functions))
    if not paragraphs:
        paragraphs.append("No module docstring and no public classes or functions.")
    return "\n\n".join(paragraphs)


def render_mirror_markdown(
    parsed: ParsedModule,
    source_text: str,
    document: MirrorDocument,
    *,
    summary: bool = False,
) -> str:
    """Render one deterministic AKMS file-level mirror without filesystem mutation.

    ``summary`` opens the body with a ``## Summary`` section, which routing mode
    loads in place of the mirror. It is off by default because mirror bytes are a
    pinned contract: see ``export.mirror_summary``.
    """

    if sha256_text(source_text) != document.source_hash:
        raise ValueError("source_text does not match MirrorDocument source_hash")
    _validated_document(parsed, document)
    symbol_index = [
        _symbol_metadata(symbol)
        for symbol in sorted(
            parsed.symbols,
            key=lambda item: (item.start_line, item.end_line, item.symbol_id),
        )
    ]
    symbol_json = json.dumps(symbol_index, indent=2, ensure_ascii=False)
    symbol_fence = _markdown_fence(symbol_json)
    source_fence = _markdown_fence(source_text)
    source_ending = "" if source_text.endswith("\n") else "\n"
    summary_section = (
        f"## Summary\n\n{render_mirror_summary(parsed)}\n\n" if summary else ""
    )

    frontmatter = _dump_frontmatter(document)
    body = (
        f"# {_markdown_path(document.source_path)}\n\n"
        f"_Mirror generated: {document.generated_at} · phase {document.phase}_\n\n"
        f"{summary_section}"
        "## Symbol Index\n\n"
        f"{symbol_fence}json\n{symbol_json}\n{symbol_fence}\n\n"
        "## Complete Source\n\n"
        f"{source_fence}{document.language}\n"
        f"{source_text}{source_ending}{source_fence}\n"
    )
    return f"---\n{frontmatter}---\n{body}"


def atomic_write_text(path: Path | str, content: str) -> None:
    """Atomically replace ``path`` with UTF-8 ``content`` from a sibling temporary file.

    The temporary file is created like any ordinary file, so the mirror gets the
    permissions the process umask gives, not a fixed mode.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        while True:
            candidate = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
            try:
                handle = open(candidate, "x", encoding="utf-8")
            except FileExistsError:
                continue
            temporary = candidate
            break
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def write_mirror_document(
    *,
    parsed: ParsedModule,
    source_text: str,
    output_root: Path | str,
    phase: int,
    generated_at: datetime | str,
) -> WrittenRecord:
    """Render and atomically write one mirror, returning its structured export record."""

    document = build_mirror_document(
        source_path=parsed.source_file.path,
        language=parsed.source_file.language,
        source_hash=parsed.source_file.content_hash,
        phase=phase,
        generated_at=generated_at,
    )
    markdown = render_mirror_markdown(parsed, source_text, document)
    atomic_write_text(Path(output_root) / document.generated_path, markdown)
    return WrittenRecord.from_document(document)
