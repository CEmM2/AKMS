"""C++ extractor backed by Doxygen (project-scoped); parses its XML output into the shared IR.

Requires the ``doxygen`` binary; without it modules come back with empty symbols.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

from akms.repo_wiki.errors import BuildError
from akms.repo_wiki.extract.base import ProjectExtractor
from akms.repo_wiki.models import (
    Language,
    ParsedModule,
    SourceFile,
    SourceSpan,
    Symbol,
    SymbolKind,
)
from akms.repo_wiki.paths import module_name_from_path
from akms.repo_wiki.symbol_ids import build_symbol_id

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

# doxygen compound kind -> SymbolKind; struct/union/interface -> "class"; namespaces transparent.
_COMPOUND_KIND: dict[str, SymbolKind] = {
    "class": "class",
    "struct": "class",
    "union": "class",
    "interface": "class",
}
_TYPE_COMPOUNDS = frozenset({"class", "struct", "union", "interface"})
# doxygen memberdef kind -> SymbolKind; variables are "constant"; enum/typedef/define skipped.
_MEMBER_KIND: dict[str, SymbolKind] = {
    "function": "function",
    "variable": "constant",
}
# Call-target kinds only: field access (kind "constant") must not become a call edge.
_CALL_TARGET_KINDS: frozenset[SymbolKind] = frozenset({"function", "method"})
# doxygen `prot` -> visibility string; package -> internal; absent/unknown leaves it unset.
_PROT: dict[str, str] = {
    "public": "public",
    "protected": "protected",
    "private": "private",
    "package": "internal",
}
_WS = re.compile(r"\s+")

_DOXYFILE = """\
DOXYFILE_ENCODING      = UTF-8
INPUT                  = "{root}"
RECURSIVE              = YES
FILE_PATTERNS          = {patterns}
STRIP_FROM_PATH        = "{root}"
GENERATE_XML           = YES
XML_OUTPUT             = xml
GENERATE_HTML          = NO
GENERATE_LATEX         = NO
XML_PROGRAMLISTING     = NO
EXTRACT_ALL            = YES
EXTRACT_PRIVATE        = YES
EXTRACT_STATIC         = YES
EXTRACT_LOCAL_CLASSES  = YES
REFERENCES_RELATION    = YES
REFERENCED_BY_RELATION = YES
RESOLVE_UNNAMED_PARAMS = YES
QUIET                  = YES
WARNINGS               = NO
WARN_IF_UNDOCUMENTED   = NO
"""


class DoxygenCppExtractor(ProjectExtractor):
    """Project-scoped C++ extractor that shells out to ``doxygen``."""

    language = Language.CPP
    extensions: tuple[str, ...] = (
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".hh",
        ".h",
        ".hxx",
    )

    def is_available(self) -> bool:
        return shutil.which("doxygen") is not None

    def tool_version(self) -> str:
        """Return the doxygen version, or ``UNKNOWN_TOOL_VERSION`` on any failure (never raises)."""
        # Lazy: ``akms.repo_wiki.manifest`` imports the registry, which registers this backend.
        from akms.repo_wiki.manifest import tool_version_or_unknown

        try:
            proc = subprocess.run(  # noqa: S603 - trusted argv, no shell
                ["doxygen", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return tool_version_or_unknown(None)
        if proc.returncode != 0:
            return tool_version_or_unknown(None)
        token = proc.stdout.strip().split()
        return tool_version_or_unknown(token[0] if token else None)

    def extract_project(
        self,
        root: str,
        files: list[str],
    ) -> dict[str, ParsedModule]:
        """Extract *files* under absolute *root*; without doxygen, modules have no symbols."""
        abs_root = str(Path(root).resolve())
        modules = {rel: self._empty_module(abs_root, rel) for rel in files}
        if not self.is_available() or not files:
            return modules

        version = self.tool_version()
        with tempfile.TemporaryDirectory() as td:
            xml_dir, error = self._run_doxygen(abs_root, td)
            if xml_dir is None:
                if error is not None:
                    for module in modules.values():
                        module.errors.append(error)
                return modules
            self._parse_xml(xml_dir, abs_root, modules, version)
        return modules

    def _run_doxygen(
        self,
        abs_root: str,
        td: str,
    ) -> tuple[Path | None, BuildError | None]:
        """Write the Doxyfile, run doxygen in *td*, return the xml dir or error."""
        patterns = " ".join(f"*{ext}" for ext in self.extensions)
        doxyfile = Path(td) / "Doxyfile"
        doxyfile.write_text(
            _DOXYFILE.format(root=abs_root, patterns=patterns),
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(  # noqa: S603 - trusted argv, no shell
                ["doxygen", str(doxyfile)],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, BuildError(
                path="<project>", stage="doxygen", message=f"doxygen failed: {exc!r}"
            )
        xml_dir = Path(td) / "xml"
        if proc.returncode != 0 or not (xml_dir / "index.xml").exists():
            return None, BuildError(
                path="<project>",
                stage="doxygen",
                message=f"doxygen produced no XML (rc={proc.returncode}): "
                f"{proc.stderr.strip()}",
            )
        return xml_dir, None

    def _parse_xml(
        self,
        xml_dir: Path,
        abs_root: str,
        modules: dict[str, ParsedModule],
        version: str,
    ) -> None:
        index = ET.parse(xml_dir / "index.xml").getroot()
        wanted = set(_COMPOUND_KIND) | {"namespace", "file"}
        refids = [
            refid
            for compound in index.findall("compound")
            if compound.get("kind") in wanted
            and (refid := compound.get("refid")) is not None
        ]
        # Namespace compound names, stripped from class qualnames (see _strip_namespace_prefix).
        namespaces = frozenset(
            name
            for compound in index.findall("compound")
            if compound.get("kind") == "namespace"
            and (name := compound.findtext("name")) is not None
        )
        module_syms: dict[str, Symbol] = {}
        seen: dict[str, set[str]] = {rel: set() for rel in modules}
        # Two-pass <references>: pass 1 records Symbols and (src, dst) refid pairs; pass 2 resolves.
        by_refid: dict[str, Symbol] = {}
        pending: list[tuple[str, str]] = []

        for refid in refids:
            cfile = xml_dir / f"{refid}.xml"
            if not cfile.exists():
                continue
            cdef = ET.parse(cfile).getroot().find("compounddef")
            if cdef is not None:
                self._parse_compound(
                    cdef,
                    abs_root,
                    modules,
                    module_syms,
                    seen,
                    by_refid,
                    pending,
                    version,
                    namespaces,
                )
        _resolve_references(by_refid, pending)

    def _parse_compound(
        self,
        cdef: "Element",
        abs_root: str,
        modules: dict[str, ParsedModule],
        module_syms: dict[str, Symbol],
        seen: dict[str, set[str]],
        by_refid: dict[str, Symbol],
        pending: list[tuple[str, str]],
        version: str,
        namespaces: frozenset[str],
    ) -> None:
        ckind = cdef.get("kind") or ""
        cname = cdef.findtext("compoundname") or ""
        loc = cdef.find("location")
        rel = self._rel(loc, abs_root)

        if ckind == "file":
            if rel is not None and rel in modules:
                mod = self._ensure_module(rel, modules, module_syms, seen)
                self._parse_members(
                    cdef,
                    "",
                    mod,
                    abs_root,
                    modules,
                    seen,
                    by_refid,
                    pending,
                    version,
                    in_type=False,
                )
            return

        if ckind == "namespace":
            # Namespaces are transparent: no symbol; recurse with an empty scope.
            if rel is not None and rel in modules:
                mod = self._ensure_module(rel, modules, module_syms, seen)
                self._parse_members(
                    cdef,
                    "",
                    mod,
                    abs_root,
                    modules,
                    seen,
                    by_refid,
                    pending,
                    version,
                    in_type=False,
                )
            return

        if rel is None or rel not in modules:
            return
        mod = self._ensure_module(rel, modules, module_syms, seen)
        kind = _COMPOUND_KIND.get(ckind, "class")
        # Strip the namespace prefix, keep class nesting: geo::Outer::Inner -> Outer::Inner.
        qualname = _strip_namespace_prefix(cname, namespaces)
        local = qualname.split("::")[-1]
        sym = self._make_symbol(
            rel=rel,
            name=local,
            qualname=qualname,
            kind=kind,
            parent_id=mod.symbol_id,
            loc=loc,
            signature=None,
            seen=seen,
            metadata=self._symbol_metadata(cdef, version),
        )
        modules[rel].symbols.append(sym)
        cid = cdef.get("id")
        if cid:
            by_refid[cid] = sym
        self._parse_members(
            cdef,
            qualname,
            sym,
            abs_root,
            modules,
            seen,
            by_refid,
            pending,
            version,
            in_type=ckind in _TYPE_COMPOUNDS,
        )

    def _parse_members(
        self,
        cdef: "Element",
        scope: str,
        parent: Symbol,
        abs_root: str,
        modules: dict[str, ParsedModule],
        seen: dict[str, set[str]],
        by_refid: dict[str, Symbol],
        pending: list[tuple[str, str]],
        version: str,
        in_type: bool,
    ) -> None:
        for sec in cdef.findall("sectiondef"):
            for member in sec.findall("memberdef"):
                mkind = member.get("kind") or ""
                if mkind not in _MEMBER_KIND:
                    continue
                loc = member.find("location")
                rel = self._rel(loc, abs_root)
                if rel is None or rel not in modules:
                    continue
                name = member.findtext("name") or "?"
                kind = _MEMBER_KIND[mkind]
                # Member functions (and constructors, which have no kind of their own) are methods.
                if kind == "function" and in_type:
                    kind = "method"
                qualname = f"{scope}::{name}" if scope else name
                sym = self._make_symbol(
                    rel=rel,
                    name=name,
                    qualname=qualname,
                    kind=kind,
                    parent_id=parent.symbol_id,
                    loc=loc,
                    signature=self._signature(member),
                    seen=seen,
                    metadata=self._symbol_metadata(member, version),
                )
                modules[rel].symbols.append(sym)
                mid = member.get("id")
                if mid:
                    by_refid[mid] = sym
                    for ref in member.findall("references"):
                        dst = ref.get("refid")
                        if dst:
                            pending.append((mid, dst))

    def _ensure_module(
        self,
        rel: str,
        modules: dict[str, ParsedModule],
        module_syms: dict[str, Symbol],
        seen: dict[str, set[str]],
    ) -> Symbol:
        existing = module_syms.get(rel)
        if existing is not None:
            return existing
        module_name = module_name_from_path(rel)
        sym = self._make_symbol(
            rel=rel,
            name=module_name,
            qualname=module_name,
            kind="module",
            parent_id=None,
            loc=None,
            signature=None,
            seen=seen,
        )
        module_syms[rel] = sym
        modules[rel].symbols.append(sym)
        return sym

    def _make_symbol(
        self,
        *,
        rel: str,
        name: str,
        qualname: str,
        kind: SymbolKind,
        parent_id: str | None,
        loc: "Element | None",
        signature: str | None,
        seen: dict[str, set[str]],
        metadata: dict[str, object] | None = None,
    ) -> Symbol:
        start, end = self._span(loc)
        symbol_id = _unique(
            build_symbol_id(self.language, rel, qualname),
            start,
            seen.setdefault(rel, set()),
        )
        return Symbol(
            symbol_id=symbol_id,
            path=rel,
            module=module_name_from_path(rel),
            name=name,
            qualname=qualname,
            kind=kind,
            parent_id=parent_id,
            start_line=start,
            end_line=end,
            signature=signature,
            docstring=None,
            span=SourceSpan(path=rel, start_line=start, end_line=end),
            language=self.language,
            metadata=dict(metadata) if metadata else {},
        )

    def _empty_module(self, abs_root: str, rel: str) -> ParsedModule:
        abs_path = str(Path(abs_root) / rel)
        source_file = SourceFile(
            path=rel,
            abs_path=abs_path,
            language=self.language.value,
            size_bytes=0,
            content_hash="",
        )
        return ParsedModule(
            source_file=source_file,
            module=module_name_from_path(rel),
            docstring=None,
            imports=[],
            symbols=[],
            errors=[],
        )

    @staticmethod
    def _rel(loc: "Element | None", abs_root: str) -> str | None:
        if loc is None:
            return None
        raw = loc.get("file")
        if not raw:
            return None
        path = Path(raw)
        if path.is_absolute():
            try:
                return path.resolve().relative_to(abs_root).as_posix()
            except ValueError:
                return None
        return path.as_posix()

    @staticmethod
    def _span(loc: "Element | None") -> tuple[int, int]:
        if loc is None:
            return 1, 1
        start = int(loc.get("bodystart") or loc.get("line") or 1)
        end = int(loc.get("bodyend") or -1)
        if end < start:
            end = int(loc.get("line") or start)
        start = max(1, start)
        return start, max(start, end)

    @staticmethod
    def _visibility(node: "Element") -> dict[str, object]:
        """Map doxygen ``prot`` to ``{"visibility": ...}``; empty if absent/unknown."""
        vis = _PROT.get(node.get("prot") or "")
        return {"visibility": vis} if vis is not None else {}

    @classmethod
    def _symbol_metadata(cls, node: "Element", version: str) -> dict[str, object]:
        """Symbol-doc metadata: visibility plus ``doxygen_version`` (never set by the fallback)."""
        metadata = cls._visibility(node)
        metadata["doxygen_version"] = version
        return metadata

    @staticmethod
    def _signature(member: "Element") -> str | None:
        defn = (member.findtext("definition") or "").strip()
        args = (member.findtext("argsstring") or "").strip()
        sig = _WS.sub(" ", f"{defn}{args}").strip()
        return sig or None


def _strip_namespace_prefix(cname: str, namespaces: frozenset[str]) -> str:
    """Strip the namespace prefix, keep class nesting: ``geo::Outer::Inner`` -> ``Outer::Inner``."""
    best = ""
    for ns in namespaces:
        prefix = f"{ns}::"
        if cname.startswith(prefix) and len(ns) > len(best):
            best = ns
    return cname[len(best) + 2 :] if best else cname


def _resolve_references(
    by_refid: dict[str, Symbol],
    pending: list[tuple[str, str]],
) -> None:
    """Resolve ``<references>`` pairs into sorted, deduped ``calls`` (mutates Symbols).

    Only function/method destinations count; data-member access (kind ``"constant"``) is dropped.
    """
    touched: dict[str, Symbol] = {}
    for src_ref, dst_ref in pending:
        src = by_refid.get(src_ref)
        dst = by_refid.get(dst_ref)
        if src is None or dst is None:
            continue
        if dst.kind not in _CALL_TARGET_KINDS:
            continue
        src.calls.append(dst.qualname)
        touched[src.symbol_id] = src
    for sym in touched.values():
        sym.calls = sorted(dict.fromkeys(sym.calls))


def _unique(candidate: str, line: int, seen: set[str]) -> str:
    """Disambiguate colliding symbol IDs with an ``@L<line>`` suffix (as ``treesitter._unique``)."""
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    suffixed = f"{candidate}@L{line}"
    seen.add(suffixed)
    return suffixed
