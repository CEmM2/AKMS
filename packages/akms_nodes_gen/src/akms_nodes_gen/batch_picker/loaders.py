"""Load Zotero BetterBibTeX export and ZotSums Obsidian frontmatter into a
single in-memory paper catalog keyed by Better-BibTeX citation key."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import frontmatter  # type: ignore[import-not-found]


_AUTHOR_TRIM = re.compile(r"\s+")


@dataclass
class Paper:
    citekey: str
    title: str
    year: str
    authors: list[str] = field(default_factory=list)
    item_type: str = ""
    doi: str = ""
    url: str = ""
    publication: str = ""
    abstract: str = ""
    tags: list[str] = field(default_factory=list)  # Zotero tags
    keywords: list[str] = field(default_factory=list)
    paper_type: str = ""
    collections: list[str] = field(default_factory=list)  # collection names
    pdf_path: str = ""  # absolute, may not exist
    has_pdf: bool = False
    summary: dict[str, str] = field(default_factory=dict)
    item_key: str = ""  # Zotero internal key

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Collection:
    name: str
    key: str
    parent_name: str
    paper_count: int
    citekeys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Catalog:
    papers: dict[str, Paper]
    collections: dict[str, Collection]

    def list_papers(self) -> list[Paper]:
        return list(self.papers.values())

    def list_collections(self) -> list[Collection]:
        return list(self.collections.values())


def _author_string(creators: list[dict[str, Any]] | None) -> list[str]:
    if not creators:
        return []
    out: list[str] = []
    for c in creators:
        if "name" in c and c["name"]:
            out.append(_AUTHOR_TRIM.sub(" ", str(c["name"])).strip())
            continue
        last = (c.get("family") or c.get("lastName") or "").strip()
        first = (c.get("given") or c.get("firstName") or "").strip()
        if last and first:
            out.append(f"{last}, {first}")
        elif last:
            out.append(last)
        elif first:
            out.append(first)
    return out


def _year_of(item: dict[str, Any]) -> str:
    date = (item.get("date") or "").strip()
    m = re.search(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b", date)
    return m.group(1) if m else ""


def _local_pdf(item: dict[str, Any]) -> str:
    """Return absolute path to a local PDF attachment, or empty string."""
    for att in item.get("attachments") or []:
        path = att.get("path") or att.get("localPath")
        if not path:
            continue
        # BBT exports absolute paths when relativeFilePaths=false (the case here)
        if path.startswith("/") and path.lower().endswith(".pdf"):
            return path
    return ""


def _load_bbt(bbt_path: Path) -> tuple[dict[str, Paper], dict[str, Collection]]:
    data = json.loads(bbt_path.read_text(encoding="utf-8"))

    cols_raw: dict[str, dict[str, Any]] = data.get("collections", {}) or {}

    # parent map: a collection record's `collections` field lists its children,
    # so derive each child's parent by reversing.
    parent_of: dict[str, str] = {}
    for parent_key, c in cols_raw.items():
        for child_key in c.get("collections") or []:
            parent_of[child_key] = parent_key
    key_to_name = {k: c.get("name", k) for k, c in cols_raw.items()}

    # Build itemID -> citekey map (BBT puts ints in cols[k].items[])
    item_id_to_citekey: dict[int, str] = {}
    papers: dict[str, Paper] = {}
    for it in data.get("items", []):
        ck = it.get("citationKey") or it.get("citekey")
        if not ck:
            continue
        item_id = it.get("itemID")
        if item_id is not None:
            item_id_to_citekey[int(item_id)] = ck

        pdf = _local_pdf(it)
        tags = [t.get("tag", "") for t in (it.get("tags") or []) if t.get("tag")]

        papers[ck] = Paper(
            citekey=ck,
            title=(it.get("title") or "").strip(),
            year=_year_of(it),
            authors=_author_string(it.get("creators")),
            item_type=it.get("itemType") or "",
            doi=(it.get("DOI") or "").strip(),
            url=(it.get("url") or "").strip(),
            publication=(it.get("publicationTitle") or "").strip(),
            abstract=(it.get("abstractNote") or "").strip(),
            tags=tags,
            pdf_path=pdf,
            has_pdf=bool(pdf),
            item_key=it.get("itemKey") or it.get("key") or "",
        )

    collections: dict[str, Collection] = {}
    for col_key, c in cols_raw.items():
        col_citekeys = [
            item_id_to_citekey[int(i)]
            for i in (c.get("items") or [])
            if int(i) in item_id_to_citekey
        ]
        parent_key = parent_of.get(col_key, "")
        col = Collection(
            name=c.get("name") or col_key,
            key=col_key,
            parent_name=key_to_name.get(parent_key, ""),
            paper_count=len(col_citekeys),
            citekeys=col_citekeys,
        )
        # Two collections can share a name in different parents; disambiguate.
        existing = collections.get(col.name)
        if existing is not None:
            # merge memberships so paper.collections still finds it
            merged = list(dict.fromkeys(existing.citekeys + col_citekeys))
            existing.citekeys = merged
            existing.paper_count = len(merged)
        else:
            collections[col.name] = col
        for citekey in col_citekeys:
            paper = papers.get(citekey)
            if paper and col.name not in paper.collections:
                paper.collections.append(col.name)

    return papers, collections


_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")


def _parse_zotsum_md(md: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (frontmatter_dict, sections_dict) for a Papers/@<citekey>.md file."""
    try:
        post = frontmatter.load(md)
    except Exception:
        return {}, {}

    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in post.content.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return dict(post.metadata), sections


def _enrich_with_zotsums(papers: dict[str, Paper], zotsums_root: Path) -> None:
    papers_dir = zotsums_root / "Papers"
    if not papers_dir.is_dir():
        return
    for md in papers_dir.glob("@*.md"):
        # filename is @<citekey>.md
        citekey = md.stem.lstrip("@")
        paper = papers.get(citekey)
        if paper is None:
            continue
        meta, sections = _parse_zotsum_md(md)
        kw = meta.get("keywords")
        if isinstance(kw, list):
            paper.keywords = [str(k).strip() for k in kw if str(k).strip()]
        elif isinstance(kw, str) and kw.strip():
            paper.keywords = [kw.strip()]
        ptype = meta.get("paper_type")
        if isinstance(ptype, str):
            paper.paper_type = ptype.strip().strip('"')
        # capture canonical sections only (and trim "*Pending*" placeholders)
        for k in ("Problem", "Methods", "Key Findings", "Limitations"):
            v = sections.get(k, "").strip()
            if v and v != "*Pending*" and v != "*None noted*":
                paper.summary[k] = v


def load_catalog(bbt_path: Path, zotsums_root: Path) -> Catalog:
    papers, collections = _load_bbt(bbt_path)
    _enrich_with_zotsums(papers, zotsums_root)
    return Catalog(papers=papers, collections=collections)
