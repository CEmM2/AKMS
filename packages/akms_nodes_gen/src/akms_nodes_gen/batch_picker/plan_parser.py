"""Parse generation_plan.md into a list of batch records.

The plan file has a regular structure:

    # Round N: Title
    **Theme:** ...
    **Subdomain:** ...
    **Dependencies:** ...

    ## Rn_Bm — Batch Title (K nodes)
    **PDF folder:** AKMS_Sources/new/Rn_Bm_<slug>/
    **Sources:** <free text>
    **ZotSums:** <free text>            (optional)
    **Missing sources (...):** <free text>   (optional)
    **Cross-references:** <free text>   (optional)

    | # | Node ID | Title | Key Concepts | Size |
    |---|---------|-------|--------------|------|
    | 14 | `kinematics-...` | Title | concepts | medium |
    ...

We are tolerant about minor format drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_BATCH_HEADER = re.compile(
    r"^##\s+(?P<id>R\d+_B\d+)\s*[—\-]\s*(?P<title>.+?)\s*\((?P<n>\d+)\s*nodes?\)\s*$"
)
_ROUND_HEADER = re.compile(r"^#\s+Round\s+(?P<r>\d+):\s*(?P<title>.+?)\s*$")
_FIELD = re.compile(r"^\*\*(?P<name>[^*]+?):\*\*\s*(?P<value>.+?)\s*$")
_TABLE_ROW = re.compile(r"^\s*\|")
_NODE_ID = re.compile(r"`([^`]+)`")
_PDF_FOLDER = re.compile(r"AKMS_Sources/new/(?P<slug>[^/`)\s]+)/?")


@dataclass
class BatchNode:
    node_id: str
    title: str
    size: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Batch:
    id: str  # e.g. "R3_B2"
    round: int
    round_title: str
    round_theme: str
    round_subdomain: str
    title: str
    node_count: int  # declared in header
    pdf_slug: str  # "R3_B2_element_technology_nonlinear"
    sources_text: str  # free-text source line from the plan
    zotsums_text: str
    missing_text: str
    cross_refs_text: str
    nodes: list[BatchNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["nodes"] = [n.to_dict() for n in self.nodes]
        return d


def _slug_from_pdf_folder(value: str) -> str:
    m = _PDF_FOLDER.search(value)
    return m.group("slug") if m else ""


def _parse_node_table(lines: list[str], start: int) -> tuple[list[BatchNode], int]:
    """Parse a single GFM table starting at or after `start`, return nodes and
    the index of the first line after the table."""
    i = start
    # find first table row
    while i < len(lines) and not _TABLE_ROW.match(lines[i]):
        i += 1
    if i >= len(lines):
        return [], i
    # header
    header_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
    i += 1
    # separator
    if i < len(lines) and re.match(r"^\s*\|[-:\s|]+\|\s*$", lines[i]):
        i += 1

    # locate the columns we want
    def col(name_options: list[str]) -> int | None:
        low = [c.lower() for c in header_cells]
        for n in name_options:
            if n in low:
                return low.index(n)
        return None

    id_col = col(["node id", "id"])
    title_col = col(["title"])
    size_col = col(["size"])

    nodes: list[BatchNode] = []
    while i < len(lines) and _TABLE_ROW.match(lines[i]):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if id_col is not None and id_col < len(cells):
            m = _NODE_ID.search(cells[id_col])
            node_id = m.group(1) if m else cells[id_col]
            title = (
                cells[title_col].strip()
                if title_col is not None and title_col < len(cells)
                else ""
            )
            size = (
                cells[size_col].strip()
                if size_col is not None and size_col < len(cells)
                else ""
            )
            if node_id and not node_id.startswith("#"):
                nodes.append(BatchNode(node_id=node_id, title=title, size=size))
        i += 1
    return nodes, i


def parse_plan(plan_path: Path) -> list[Batch]:
    text = plan_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    batches: list[Batch] = []

    cur_round = 0
    cur_round_title = ""
    cur_round_theme = ""
    cur_round_subdomain = ""

    i = 0
    while i < len(lines):
        line = lines[i]

        m_round = _ROUND_HEADER.match(line)
        if m_round:
            cur_round = int(m_round.group("r"))
            cur_round_title = m_round.group("title").strip()
            cur_round_theme = ""
            cur_round_subdomain = ""
            i += 1
            # collect round-level **field**: lines until first batch or next round header
            while i < len(lines):
                ln = lines[i]
                if _BATCH_HEADER.match(ln) or _ROUND_HEADER.match(ln):
                    break
                fm = _FIELD.match(ln)
                if fm:
                    name = fm.group("name").strip().lower()
                    val = fm.group("value").strip()
                    if name == "theme":
                        cur_round_theme = val
                    elif name == "subdomain":
                        cur_round_subdomain = val
                i += 1
            continue

        m_batch = _BATCH_HEADER.match(line)
        if m_batch:
            batch = Batch(
                id=m_batch.group("id"),
                round=cur_round,
                round_title=cur_round_title,
                round_theme=cur_round_theme,
                round_subdomain=cur_round_subdomain,
                title=m_batch.group("title").strip(),
                node_count=int(m_batch.group("n")),
                pdf_slug="",
                sources_text="",
                zotsums_text="",
                missing_text="",
                cross_refs_text="",
            )
            i += 1
            # collect fields and the first table until we hit the next batch / round / hr
            while i < len(lines):
                ln = lines[i]
                if (
                    _BATCH_HEADER.match(ln)
                    or _ROUND_HEADER.match(ln)
                    or ln.strip() == "---"
                ):
                    break
                fm = _FIELD.match(ln)
                if fm:
                    name = fm.group("name").strip().lower()
                    val = fm.group("value").strip()
                    if name.startswith("pdf folder"):
                        batch.pdf_slug = _slug_from_pdf_folder(val)
                    elif name == "sources":
                        batch.sources_text = val
                    elif name == "zotsums":
                        batch.zotsums_text = val
                    elif name.startswith("missing sources"):
                        batch.missing_text = val
                    elif name == "cross-references":
                        batch.cross_refs_text = val
                if _TABLE_ROW.match(ln) and not batch.nodes:
                    nodes, j = _parse_node_table(lines, i)
                    batch.nodes = nodes
                    i = j
                    continue
                i += 1
            batches.append(batch)
            continue

        i += 1

    return batches
