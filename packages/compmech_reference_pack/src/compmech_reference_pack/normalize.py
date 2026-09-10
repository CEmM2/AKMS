"""normalize.py — rewrite human-authored algpseudocode into algo2code-clean form.

The Tier-2 adapter's pre-processing core. An LSP node's
``extracted["implementation"]`` is human/markdown-authored algpseudocode;
``algo2code.transpile`` expects an ``algorithmic`` block optionally preceded by
``% algorithm/backend/args/type`` directive lines.

What this pass actually does
----------------------------
Empirically, MechDSL's current ``algo2code`` expression grammar already
subsumes the rewrites the original plan anticipated (``\\sqrt{3/2}``,
``\\frac{a}{b}``, ``\\cdot``, ``\\left/\\right``, Greek letters, ``^{...}``,
and ``\\If/\\Else/\\ElsIf/\\While/\\For`` control flow all transpile as-is).
So the genuinely-useful work here is:

1. **Extract** the ``\\begin{algorithmic} … \\end{algorithmic}`` block out of
   surrounding markdown (prose, code fences) so the source is bounded and the
   *absence* of an algorithm is detectable (``algo2code`` silently emits an
   empty function otherwise).
2. **Synthesise directives** — prepend ``% algorithm <name>`` / ``% backend
   taichi`` when the author didn't, so the emitted function is meaningfully
   named instead of the ``algo2code`` default ``algorithm``; author-supplied
   directives are preserved.
3. **Surface parser failures as structured warnings, never raise** — per spec
   09 §7 rule 5 (a failed adapter must not invalidate the packet unless
   executable output was explicitly required).

The public deliverable is :func:`normalize_algpseudocode` (``str -> str``);
:func:`normalize` wraps it with a trial parse and the warning report the
adapter consumes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "NormalizationResult",
    "extract_algorithmic_block",
    "normalize",
    "normalize_algpseudocode",
]

_ALGORITHMIC_RE = re.compile(
    r"\\begin\{algorithmic\}(?:\[[^\]]*\])?(?P<body>.*?)\\end\{algorithmic\}",
    re.DOTALL,
)
_FENCE_RE = re.compile(r"^[ \t]*```[^\n]*$", re.MULTILINE)
# ":=" is the only assignment arrow algo2code does not accept; "\gets" and
# "\leftarrow" parse natively but we canonicalise all three to "=".
_ARROW_RE = re.compile(r":=|\\gets|\\leftarrow")
_DIRECTIVE_KEYWORDS = frozenset({"algorithm", "backend", "args", "type"})


@dataclass(frozen=True)
class NormalizationResult:
    """Outcome of normalising one implementation excerpt.

    Attributes
    ----------
    normalized:
        algo2code-ready source (synthesised directives + algorithmic block).
    algorithmic_block_found:
        Whether an ``\\begin{algorithmic}`` block was present in the input.
    parses:
        Whether ``algo2code.parse_algorithm`` accepted the normalised source.
    warnings:
        Structured, human-readable warnings (missing block, parse errors).
        Never empty when ``parses`` is ``False`` or the block was absent.
    """

    normalized: str
    algorithmic_block_found: bool
    parses: bool
    warnings: tuple[str, ...] = ()


def extract_algorithmic_block(impl_md: str) -> str | None:
    """Return the inner body of the first ``algorithmic`` block, or ``None``.

    Markdown code fences are stripped first so a fenced ``\\begin{algorithmic}``
    is still found. The returned body excludes the ``\\begin``/``\\end`` markers.
    """
    if not impl_md:
        return None
    text = _FENCE_RE.sub("", impl_md)
    match = _ALGORITHMIC_RE.search(text)
    if match is None:
        return None
    return match.group("body").strip("\n")


def _sanitize_identifier(name: str) -> str:
    """Coerce an arbitrary string into a safe algo2code algorithm identifier."""
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", name).strip("_")
    if not cleaned:
        return "algorithm"
    if cleaned[0].isdigit():
        cleaned = f"a_{cleaned}"
    return cleaned


def _collect_directives(impl_md: str) -> list[str]:
    """Collect author-supplied ``% algorithm/backend/args/type`` directives.

    Only lines *before* the algorithmic block are considered, so ``%`` lines
    that happen to live inside the block are not mistaken for directives.
    """
    head = impl_md
    begin = impl_md.find(r"\begin{algorithmic}")
    if begin != -1:
        head = impl_md[:begin]
    directives: list[str] = []
    for raw in head.splitlines():
        stripped = raw.strip()
        if not stripped.startswith("%"):
            continue
        content = stripped[1:].strip()
        first = content.split(None, 1)[0] if content else ""
        if first in _DIRECTIVE_KEYWORDS:
            directives.append(content)
    return directives


def normalize_algpseudocode(impl_md: str, *, algorithm_name: str | None = None) -> str:
    """Rewrite a human-authored implementation excerpt into algo2code source.

    Extracts the ``algorithmic`` block, canonicalises assignment arrows, and
    prepends synthesised ``% algorithm``/``% backend`` directives (preserving
    any the author already supplied). Never raises: a missing block yields an
    empty algorithmic shell, which :func:`normalize` flags as a warning.
    """
    body = extract_algorithmic_block(impl_md)
    if body is None:
        body = ""
    body = _ARROW_RE.sub("=", body)

    existing = _collect_directives(impl_md)
    # Match both "algorithm <name>" and a bare "algorithm" directive so a
    # name-less author directive doesn't get a synthesised one appended too.
    has_name = any(d == "algorithm" or d.startswith("algorithm ") for d in existing)
    has_backend = any(d == "backend" or d.startswith("backend ") for d in existing)

    lines: list[str] = []
    if not has_name:
        lines.append(
            f"% algorithm {_sanitize_identifier(algorithm_name or 'algorithm')}"
        )
    if not has_backend:
        lines.append("% backend taichi")
    lines.extend(f"% {d}" for d in existing)
    lines.append(r"\begin{algorithmic}")
    if body:
        lines.append(body)
    lines.append(r"\end{algorithmic}")
    return "\n".join(lines)


def normalize(
    impl_md: str, *, algorithm_name: str | None = None
) -> NormalizationResult:
    """Normalise an excerpt and report parse status + structured warnings.

    Wraps :func:`normalize_algpseudocode` with a trial ``algo2code`` parse so
    the adapter can attach warnings without ever crashing the packet.
    """
    found = extract_algorithmic_block(impl_md) is not None
    normalized = normalize_algpseudocode(impl_md, algorithm_name=algorithm_name)

    warnings: list[str] = []
    if not found:
        warnings.append(
            r"no \begin{algorithmic} block found in implementation excerpt; "
            "emitted source will be an empty function"
        )

    parses = False
    try:
        from algo2code import parse_algorithm

        parse_algorithm(normalized)
        parses = True
    except Exception as exc:
        warnings.append(f"algo2code parse failed: {type(exc).__name__}: {exc}")

    return NormalizationResult(
        normalized=normalized,
        algorithmic_block_found=found,
        parses=parses,
        warnings=tuple(warnings),
    )
