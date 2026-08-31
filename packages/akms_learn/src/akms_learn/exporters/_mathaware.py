"""Math + algorithm aware markdown rendering for the rich HTML export.

Section content carries LaTeX math (``$...$``, ``$$...$$``, ``\\(...\\)``,
``\\[...\\]``) and ``\\begin{algorithmic}`` pseudocode. markdown-it on its own
eats the backslashes and turns underscores into ``<em>``, so we pull math and
algorithm blocks OUT before markdown rendering and restore them afterwards:

* algorithm blocks render to self-contained ``<div class="algo">`` markup
  (no JS); the inline ``$...$`` math inside each step is left for MathJax;
* math is restored as escaped delimiters that the rich template's MathJax
  script typesets in the browser.

This mirrors the proven ``dev/demos/lessons/build_lesson_html.py`` renderer so
the rich HTML export and the showcase lessons stay visually consistent. Only
the rich export imports this module — the default offline preview never does,
so its self-contained / no-JS guarantee is untouched.
"""

from __future__ import annotations

import html as _html
import re

from markdown_it import MarkdownIt

__all__ = ["render_markdown"]

_MD = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")

_ALGO_RE = re.compile(
    r"(?:\$\$\s*)?\\begin\{algorithmic\}(.*?)\\end\{algorithmic\}(?:\s*\$\$)?", re.S
)
_FOR_RE = re.compile(r"^\\(For|While|If)\{(.*)\}\s*$")
_RETURN_RE = re.compile(r"^\\Return\b\s*(.*)$")
_END_RE = re.compile(r"^\\(EndFor|EndWhile|EndIf)\b")
_PH = "@@AKMSMJX{0}@@"


def _esc(s: str) -> str:
    return _html.escape(s, quote=False)


def _render_algo(inner: str) -> str:
    lines: list[tuple[int, str]] = []
    indent = 0
    for raw in inner.splitlines():
        s = raw.strip()
        if not s:
            continue
        if _END_RE.match(s):
            indent = max(0, indent - 1)
            continue
        if s.startswith("\\Else"):
            lines.append((max(0, indent - 1), '<span class="kw">else</span>'))
            continue
        m = _FOR_RE.match(s)
        if m:
            lines.append(
                (
                    indent,
                    '<span class="kw">'
                    + m.group(1).lower()
                    + "</span> "
                    + _esc(m.group(2))
                    + ' <span class="kw">do</span>',
                )
            )
            indent += 1
            continue
        m = _RETURN_RE.match(s)
        if m:
            lines.append((indent, '<span class="kw">return</span> ' + _esc(m.group(1))))
            continue
        if s.startswith("\\State"):
            content = s[6:].strip()
            # some source nodes ship empty State placeholders (`\State $$`); blank them
            lines.append(
                (indent, "&nbsp;" if content.strip("$ ") == "" else _esc(content))
            )
            continue
        if s.startswith("\\Comment"):
            continue
        lines.append((indent, _esc(re.sub(r"^\\[A-Za-z]+\s*", "", s))))
    rows = "".join(
        '<div class="algo-line" style="padding-left:%.2fem">%s</div>'
        % (0.2 + ind * 1.6, b or "&nbsp;")
        for ind, b in lines
    )
    return '<div class="algo">' + rows + "</div>"


def _prepare(md: str) -> tuple[str, list[str]]:
    store: list[str] = []

    def keep(h: str) -> str:
        store.append(h)
        return _PH.format(len(store) - 1)

    md = _ALGO_RE.sub(lambda m: "\n\n" + keep(_render_algo(m.group(1))) + "\n\n", md)
    md = re.sub(r"\$\$(.+?)\$\$", lambda m: keep(_esc(m.group(0))), md, flags=re.S)
    md = re.sub(r"\\\[(.+?)\\\]", lambda m: keep(_esc(m.group(0))), md, flags=re.S)
    md = re.sub(r"\$(?!\d)(.+?)\$", lambda m: keep(_esc(m.group(0))), md)
    md = re.sub(r"\\\((.+?)\\\)", lambda m: keep(_esc(m.group(0))), md, flags=re.S)
    return md, store


def render_markdown(text: str) -> str:
    """Render section markdown to HTML with math + algorithms preserved.

    Returns trusted HTML (the caller marks it ``| safe`` in the Jinja template);
    inline/display math survives as escaped LaTeX delimiters for MathJax.
    """
    if not text or not str(text).strip():
        return '<p class="empty-marker">_no content_</p>'
    prepared, store = _prepare(text)
    body = _MD.render(prepared)
    for i, h in enumerate(store):
        body = body.replace("<p>" + _PH.format(i) + "</p>", h).replace(_PH.format(i), h)
    return body
