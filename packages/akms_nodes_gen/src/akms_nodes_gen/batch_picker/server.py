"""FastAPI server for the AKMS batch-picker UI."""

from __future__ import annotations

import re
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Paths
from .exporters import (
    create_notebook_and_upload,
    stage_pdfs,
    write_plan_json,
)
from .loaders import Catalog, Paper, load_catalog
from .plan_parser import Batch, parse_plan
from .queries import (
    SavedQuery,
    load_queries,
    save_queries,
    upsert as upsert_query,
)
from .state import (
    BatchAssignment,
    get_or_create,
    load_state,
    save_state,
    stamp_synced,
)


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "onto",
    "this",
    "that",
    "their",
    "these",
    "those",
    "are",
    "was",
    "were",
    "have",
    "has",
    "had",
    "but",
    "not",
    "any",
    "all",
    "via",
    "per",
    "based",
    "using",
    "use",
    "uses",
    "about",
    "between",
    "across",
    "method",
    "methods",
    "approach",
    "model",
    "models",
    "study",
    "paper",
    "research",
    "analysis",
    "results",
    "section",
    "ch",
}


def _tokenize(s: str) -> list[str]:
    return [
        t.lower() for t in _TOKEN_RE.findall(s or "") if t.lower() not in _STOPWORDS
    ]


# ---------------------------------------------------------------------------
# Pydantic request / shared models
# ---------------------------------------------------------------------------


class FilterSpec(BaseModel):
    """Re-usable paper-search filter. Same shape that /api/papers accepts as
    query parameters and that saved queries persist."""

    q: str = ""
    collection: list[str] = Field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    item_type: str = ""
    only_with_pdf: bool = False
    suggest_for: str = ""


class PaperListRequest(BaseModel):
    papers: list[str]


class CitekeysRequest(BaseModel):
    citekeys: list[str]


class MoveRequest(BaseModel):
    from_batch: str
    citekeys: list[str]


class BulkAddRequest(BaseModel):
    filter: FilterSpec
    mode: str = "add"  # "add" or "replace"
    limit: int = 1000


class SaveQueryRequest(BaseModel):
    filter: FilterSpec


class CreateNotebookRequest(BaseModel):
    upload: bool = True
    wait: bool = False


class StagePdfsRequest(BaseModel):
    use_symlink: bool = True


# ---------------------------------------------------------------------------
# Repo
# ---------------------------------------------------------------------------


class _Repo:
    """In-memory glue. Reloads catalog/plan on demand."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.lock = RLock()
        self.catalog: Catalog | None = None
        self.batches: list[Batch] = []
        self.batch_index: dict[str, Batch] = {}
        self.state: dict[str, BatchAssignment] = {}
        self.queries: dict[str, SavedQuery] = {}

    def load(self) -> None:
        with self.lock:
            self.catalog = load_catalog(self.paths.bbt_json, self.paths.zotsums_root)
            self.batches = parse_plan(self.paths.plan_md)
            self.batch_index = {b.id: b for b in self.batches}
            self.state = load_state(self.paths.state_file)
            self.queries = load_queries(self.paths.queries_file)

    def get_batch(self, batch_id: str) -> Batch:
        b = self.batch_index.get(batch_id)
        if b is None:
            raise HTTPException(404, f"Unknown batch {batch_id}")
        return b

    def assignment(self, batch_id: str) -> BatchAssignment:
        with self.lock:
            return get_or_create(self.state, batch_id)

    def save_state(self) -> None:
        with self.lock:
            save_state(self.paths.state_file, self.state)

    def save_queries(self) -> None:
        with self.lock:
            save_queries(self.paths.queries_file, self.queries)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _paper_card(paper: Paper, repo: _Repo) -> dict[str, Any]:
    """Lightweight projection for the list table."""
    assigned_to: list[str] = []
    for bid, a in repo.state.items():
        if paper.citekey in a.papers:
            assigned_to.append(bid)
    return {
        "citekey": paper.citekey,
        "title": paper.title,
        "year": paper.year,
        "authors": paper.authors[:3],
        "n_authors": len(paper.authors),
        "item_type": paper.item_type,
        "paper_type": paper.paper_type,
        "keywords": paper.keywords,
        "tags": paper.tags,
        "collections": paper.collections,
        "has_pdf": paper.has_pdf,
        "assigned_to": assigned_to,
    }


def _batch_card(b: Batch, repo: _Repo) -> dict[str, Any]:
    a = repo.state.get(b.id)
    n_assigned = len(a.papers) if a else 0
    has_nb = bool(a and a.nlm_notebook_id)
    n_uploaded = len(a.uploaded_papers) if a else 0
    return {
        "id": b.id,
        "round": b.round,
        "round_title": b.round_title,
        "title": b.title,
        "node_count": b.node_count,
        "n_nodes_parsed": len(b.nodes),
        "pdf_slug": b.pdf_slug,
        "n_assigned": n_assigned,
        "has_notebook": has_nb,
        "notebook_id": (a.nlm_notebook_id if a else "") or "",
        "n_uploaded": n_uploaded,
    }


def _score_paper(paper: Paper, batch_tokens: set[str]) -> int:
    if not batch_tokens:
        return 0
    text_tokens: set[str] = set()
    text_tokens.update(_tokenize(paper.title))
    for k in paper.keywords:
        text_tokens.update(_tokenize(k))
    for t in paper.tags:
        text_tokens.update(_tokenize(t))
    text_tokens.update(_tokenize(paper.abstract))
    return len(batch_tokens & text_tokens)


def _batch_tokens(b: Batch) -> set[str]:
    bag: set[str] = set()
    bag.update(_tokenize(b.title))
    bag.update(_tokenize(b.round_title))
    bag.update(_tokenize(b.round_theme))
    for n in b.nodes:
        bag.update(_tokenize(n.title))
        bag.update(_tokenize(n.node_id.replace("-", " ")))
    bag.update(_tokenize(b.zotsums_text))
    bag.update(_tokenize(b.sources_text))
    return bag


def _filter_papers(repo: _Repo, spec: FilterSpec) -> list[tuple[int, Paper]]:
    """Apply a FilterSpec to the catalog. Returns a sorted list of
    (score, paper) — score is non-zero only when ``suggest_for`` is set."""
    assert repo.catalog is not None
    cat = repo.catalog
    query = spec.q.strip().lower()
    col_set = set(spec.collection)
    batch_tokens: set[str] = set()
    if spec.suggest_for:
        target = repo.batch_index.get(spec.suggest_for)
        if target is not None:
            batch_tokens = _batch_tokens(target)

    out: list[tuple[int, Paper]] = []
    for paper in cat.papers.values():
        if spec.only_with_pdf and not paper.has_pdf:
            continue
        if spec.item_type and paper.item_type != spec.item_type:
            continue
        if col_set and not (col_set & set(paper.collections)):
            continue
        if spec.year_from and (not paper.year or int(paper.year) < spec.year_from):
            continue
        if spec.year_to and (not paper.year or int(paper.year) > spec.year_to):
            continue
        if query:
            hay = " ".join(
                [
                    paper.citekey,
                    paper.title,
                    " ".join(paper.authors),
                    " ".join(paper.keywords),
                    " ".join(paper.tags),
                    paper.abstract,
                ]
            ).lower()
            if query not in hay:
                continue
        score = _score_paper(paper, batch_tokens) if batch_tokens else 0
        out.append((score, paper))

    if batch_tokens:
        out.sort(key=lambda r: (-r[0], r[1].citekey))
    else:
        out.sort(key=lambda r: r[1].citekey)
    return out


def _dedup(seq: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _query_card(q: SavedQuery) -> dict[str, Any]:
    return {
        "name": q.name,
        "filter": q.filter,
        "created_at": q.created_at,
        "updated_at": q.updated_at,
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def create_app(paths: Paths | None = None) -> FastAPI:
    paths = paths or Paths.resolve()
    repo = _Repo(paths)
    repo.load()

    app = FastAPI(title="AKMS Batch Picker")
    static_dir = Path(__file__).resolve().parent / "static"

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ---- meta -------------------------------------------------------------

    @app.post("/api/reload")
    def reload_all() -> dict[str, Any]:
        repo.load()
        assert repo.catalog is not None
        return {
            "papers": len(repo.catalog.papers),
            "collections": len(repo.catalog.collections),
            "batches": len(repo.batches),
            "state_batches": len(repo.state),
            "saved_queries": len(repo.queries),
        }

    @app.get("/api/config")
    def config() -> dict[str, str]:
        return {
            "repo_root": str(paths.repo_root),
            "plan_md": str(paths.plan_md),
            "bbt_json": str(paths.bbt_json),
            "zotsums_root": str(paths.zotsums_root),
            "state_file": str(paths.state_file),
            "queries_file": str(paths.queries_file),
            "inputs_dir": str(paths.inputs_dir),
            "sources_dir": str(paths.sources_dir),
        }

    # ---- batches & assignments -------------------------------------------

    @app.get("/api/batches")
    def list_batches() -> list[dict[str, Any]]:
        return [_batch_card(b, repo) for b in repo.batches]

    @app.get("/api/batches/{batch_id}")
    def get_batch(batch_id: str) -> dict[str, Any]:
        b = repo.get_batch(batch_id)
        a = repo.assignment(batch_id)
        assert repo.catalog is not None
        papers = [
            _paper_card(repo.catalog.papers[ck], repo)
            for ck in a.papers
            if ck in repo.catalog.papers
        ]
        unknown = [ck for ck in a.papers if ck not in repo.catalog.papers]
        return {
            "batch": b.to_dict(),
            "assignment": a.to_dict(),
            "papers": papers,
            "unknown_citekeys": unknown,
        }

    @app.put("/api/batches/{batch_id}/papers")
    def set_batch_papers(batch_id: str, body: PaperListRequest) -> dict[str, Any]:
        repo.get_batch(batch_id)
        a = repo.assignment(batch_id)
        a.papers = _dedup(body.papers)
        repo.save_state()
        return {"papers": a.papers}

    @app.post("/api/batches/{batch_id}/papers/add")
    def add_batch_papers(batch_id: str, body: CitekeysRequest) -> dict[str, Any]:
        repo.get_batch(batch_id)
        a = repo.assignment(batch_id)
        before = set(a.papers)
        a.papers = _dedup(list(a.papers) + list(body.citekeys))
        added = [ck for ck in body.citekeys if ck not in before]
        repo.save_state()
        return {"papers": a.papers, "added": added, "n_added": len(added)}

    @app.post("/api/batches/{batch_id}/papers/remove")
    def remove_batch_papers(batch_id: str, body: CitekeysRequest) -> dict[str, Any]:
        repo.get_batch(batch_id)
        a = repo.assignment(batch_id)
        drop = set(body.citekeys)
        before = a.papers
        a.papers = [ck for ck in before if ck not in drop]
        # Also clear from uploaded_papers since they're no longer attached
        a.uploaded_papers = [ck for ck in a.uploaded_papers if ck not in drop]
        removed = [ck for ck in before if ck in drop]
        repo.save_state()
        return {"papers": a.papers, "removed": removed, "n_removed": len(removed)}

    @app.post("/api/batches/{batch_id}/papers/move")
    def move_papers(batch_id: str, body: MoveRequest) -> dict[str, Any]:
        """Move citekeys from ``from_batch`` to ``batch_id`` atomically (single save)."""
        repo.get_batch(batch_id)
        repo.get_batch(body.from_batch)
        if batch_id == body.from_batch:
            raise HTTPException(400, "from_batch must differ from target")
        target = repo.assignment(batch_id)
        source = repo.assignment(body.from_batch)
        drop = set(body.citekeys)
        before_target = set(target.papers)
        target.papers = _dedup(list(target.papers) + list(body.citekeys))
        added = [ck for ck in body.citekeys if ck not in before_target]
        before_source = source.papers
        source.papers = [ck for ck in before_source if ck not in drop]
        source.uploaded_papers = [ck for ck in source.uploaded_papers if ck not in drop]
        removed = [ck for ck in before_source if ck in drop]
        repo.save_state()
        return {
            "target_papers": target.papers,
            "source_papers": source.papers,
            "n_added": len(added),
            "n_removed_from_source": len(removed),
        }

    @app.post("/api/batches/{batch_id}/bulk_add")
    def bulk_add(batch_id: str, body: BulkAddRequest) -> dict[str, Any]:
        repo.get_batch(batch_id)
        a = repo.assignment(batch_id)
        results = _filter_papers(repo, body.filter)
        if body.limit > 0:
            results = results[: body.limit]
        matched = [p.citekey for _, p in results]
        if body.mode == "replace":
            before = set(a.papers)
            a.papers = _dedup(matched)
            added = [ck for ck in matched if ck not in before]
            removed = [ck for ck in before if ck not in set(matched)]
            a.uploaded_papers = [ck for ck in a.uploaded_papers if ck in set(a.papers)]
        elif body.mode == "add":
            before = set(a.papers)
            a.papers = _dedup(list(a.papers) + matched)
            added = [ck for ck in matched if ck not in before]
            removed = []
        else:
            raise HTTPException(
                400, f"Unknown mode {body.mode!r}; use 'add' or 'replace'"
            )
        repo.save_state()
        return {
            "papers": a.papers,
            "n_matched": len(matched),
            "n_added": len(added),
            "n_removed": len(removed),
            "added": added,
            "removed": removed,
            "mode": body.mode,
        }

    # ---- compare ----------------------------------------------------------

    @app.get("/api/batches/{batch_id}/compare/{other_id}")
    def compare_batches(batch_id: str, other_id: str) -> dict[str, Any]:
        repo.get_batch(batch_id)
        repo.get_batch(other_id)
        a = repo.assignment(batch_id)
        b = repo.assignment(other_id)
        a_set = set(a.papers)
        b_set = set(b.papers)
        assert repo.catalog is not None
        catalog = repo.catalog

        def card(ck: str) -> dict[str, Any]:
            paper = catalog.papers.get(ck)
            if paper is None:
                return {
                    "citekey": ck,
                    "title": "(unknown citekey)",
                    "has_pdf": False,
                    "year": "",
                }
            return {
                "citekey": paper.citekey,
                "title": paper.title,
                "year": paper.year,
                "has_pdf": paper.has_pdf,
                "authors": paper.authors[:1],
            }

        return {
            "a": batch_id,
            "b": other_id,
            "both": [card(ck) for ck in a.papers if ck in b_set],
            "only_a": [card(ck) for ck in a.papers if ck not in b_set],
            "only_b": [card(ck) for ck in b.papers if ck not in a_set],
            "n_a": len(a.papers),
            "n_b": len(b.papers),
        }

    # ---- collections / papers -------------------------------------------

    @app.get("/api/collections")
    def list_collections() -> list[dict[str, Any]]:
        assert repo.catalog is not None
        return [
            {
                "name": c.name,
                "parent_name": c.parent_name,
                "paper_count": c.paper_count,
            }
            for c in sorted(
                repo.catalog.collections.values(),
                key=lambda x: (x.parent_name, x.name),
            )
            if c.paper_count > 0
        ]

    @app.get("/api/papers")
    def list_papers(
        q: str = "",
        collection: list[str] = Query(default_factory=list),
        year_from: int | None = None,
        year_to: int | None = None,
        item_type: str = "",
        only_with_pdf: bool = False,
        suggest_for: str = "",
        limit: int = 500,
    ) -> dict[str, Any]:
        spec = FilterSpec(
            q=q,
            collection=list(collection),
            year_from=year_from,
            year_to=year_to,
            item_type=item_type,
            only_with_pdf=only_with_pdf,
            suggest_for=suggest_for,
        )
        results = _filter_papers(repo, spec)
        return {
            "total": len(results),
            "limit": limit,
            "results": [
                {**_paper_card(p, repo), "score": score} for score, p in results[:limit]
            ],
        }

    @app.get("/api/papers/{citekey}")
    def get_paper(citekey: str) -> dict[str, Any]:
        assert repo.catalog is not None
        p = repo.catalog.papers.get(citekey)
        if p is None:
            raise HTTPException(404, f"Unknown paper {citekey}")
        return p.to_dict()

    # ---- saved queries ---------------------------------------------------

    @app.get("/api/saved_queries")
    def list_saved_queries() -> list[dict[str, Any]]:
        return [
            _query_card(q)
            for q in sorted(repo.queries.values(), key=lambda x: x.name.lower())
        ]

    @app.put("/api/saved_queries/{name}")
    def upsert_saved_query(name: str, body: SaveQueryRequest) -> dict[str, Any]:
        if not name.strip():
            raise HTTPException(400, "Query name cannot be empty")
        q = upsert_query(repo.queries, name, body.filter.model_dump())
        repo.save_queries()
        return _query_card(q)

    @app.delete("/api/saved_queries/{name}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_saved_query(name: str) -> Response:
        if name not in repo.queries:
            raise HTTPException(404, f"Unknown saved query {name!r}")
        del repo.queries[name]
        repo.save_queries()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ---- pipeline actions -------------------------------------------------

    @app.post("/api/batches/{batch_id}/export_plan")
    def export_plan(batch_id: str) -> dict[str, Any]:
        b = repo.get_batch(batch_id)
        a = repo.assignment(batch_id)
        assert repo.catalog is not None
        out = write_plan_json(b, a, repo.catalog, paths.inputs_dir)
        repo.save_state()
        return {"path": str(out), "n_papers": len(a.papers)}

    @app.post("/api/batches/{batch_id}/stage_pdfs")
    def stage_batch_pdfs(batch_id: str, body: StagePdfsRequest) -> dict[str, Any]:
        b = repo.get_batch(batch_id)
        a = repo.assignment(batch_id)
        assert repo.catalog is not None
        result = stage_pdfs(
            b, a, repo.catalog, paths.sources_dir, use_symlink=body.use_symlink
        )
        return {"ok": result.ok, "message": result.message, **result.data}

    @app.post("/api/batches/{batch_id}/create_notebook")
    def create_nb(
        batch_id: str, body: CreateNotebookRequest
    ) -> dict[str, Any] | JSONResponse:
        b = repo.get_batch(batch_id)
        a = repo.assignment(batch_id)
        assert repo.catalog is not None
        result = create_notebook_and_upload(
            b,
            a,
            repo.catalog,
            paths.sources_dir,
            upload=body.upload,
            wait=body.wait,
        )
        if result.ok:
            stamp_synced(a)
        repo.save_state()
        return JSONResponse(
            status_code=200 if result.ok else 502,
            content={"ok": result.ok, "message": result.message, **result.data},
        )

    return app
