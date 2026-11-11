"""A code mirror's summary, derived from the mirror when a loadout is built.

``repo-wiki export-akms`` can open a mirror with a ``## Summary`` section
(``export.mirror_summary``), but that rewrites every mirror. Each mirror already
carries a ``## Symbol Index`` and the complete source, which hold the same
facts, so the loadout generator can render the same text from them and leave the
mirror files alone.
"""

from __future__ import annotations

import ast
import inspect
import io
import json
import re
import tokenize
from types import SimpleNamespace
from typing import Any

# The index is the first fenced ``json`` block under its heading. JSON keeps
# every string on one line, so no line inside it can be the closing fence.
_SYMBOL_INDEX = re.compile(
    r"(?:\A|\n)## Symbol Index\n\n(`{3,})json\n(.*?)\n\1\n", re.DOTALL
)


_SOURCE = re.compile(r"\n## Complete Source\n\n(`{3,})([^\n`]*)\n")


def _python_docstring(source: str) -> str | None:
    """The module docstring, read from the first statement without a full parse."""
    parts: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in (tokenize.COMMENT, tokenize.NL):
                continue
            if token.type == tokenize.STRING:
                parts.append(token.string)
                continue
            if token.type in (tokenize.NEWLINE, tokenize.ENDMARKER) and parts:
                value = ast.literal_eval(" ".join(parts))
                return inspect.cleandoc(value) if isinstance(value, str) else None
            return None
    except (tokenize.TokenError, SyntaxError, ValueError):
        return None
    return None


def _module_docstring(body: str, start: int) -> str | None:
    """The docstring of a Python mirror's source; the index does not carry it."""
    match = _SOURCE.search(body, start)
    if match is None or match[2] != "python":
        return None
    source = body[match.end() :]
    end = source.rfind("\n" + match[1])
    return _python_docstring(source[:end] + "\n" if end >= 0 else source)


def _symbol(entry: dict[str, Any]) -> SimpleNamespace:
    """The fields the summary renderer reads, from one index entry."""
    symbol_id = entry["symbol_id"]
    kind = entry["kind"]
    if not isinstance(symbol_id, str) or not isinstance(kind, str):
        raise TypeError("symbol_id and kind must be strings")
    qualname = symbol_id.split("::", 1)[-1]
    return SimpleNamespace(
        symbol_id=symbol_id,
        kind=kind,
        # A module keeps its dotted name; anything else is named by its last part.
        name=qualname if kind == "module" else re.split(r"::|\.", qualname)[-1],
        start_line=int(entry["start_line"]),
        end_line=int(entry["end_line"]),
        signature=entry.get("signature"),
        docstring=entry.get("docstring"),
        parent_id=entry.get("parent_id"),
    )


def derive_mirror_summary(body: str) -> str | None:
    """Return the ``## Summary`` text the exporter would write for this mirror.

    None when the body has no symbol index that parses, so a mirror from
    another generator renders as it always has.
    """
    match = _SYMBOL_INDEX.search(body)
    if match is None:
        return None
    try:
        entries = json.loads(match[2])
        if not isinstance(entries, list):
            return None
        symbols = [_symbol(entry) for entry in entries]
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    # Imported here: the renderer lives with the exporter, which a loadout
    # without code mirrors never needs.
    from akms.repo_wiki.export.akms import render_mirror_summary

    module = next((item for item in symbols if item.kind == "module"), None)
    docstring = module.docstring if module is not None else None
    parsed: Any = SimpleNamespace(
        symbols=symbols,
        docstring=docstring or _module_docstring(body, match.end()),
    )
    return render_mirror_summary(parsed)
