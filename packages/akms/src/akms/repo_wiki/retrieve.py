"""Retrieval and context expansion over the local repo wiki index."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Literal, Protocol

from akms.repo_wiki.config import load_config
from akms.repo_wiki.index import SearchResult, search_index
from akms.repo_wiki.models import Language
from akms.repo_wiki.symbol_ids import build_symbol_id

QueryKind = Literal[
    "symbol", "path", "natural_language", "test", "architecture", "flow", "where"
]


@dataclass(slots=True)
class NormalizedQuery:
    raw: str
    text: str
    kind: QueryKind
    exact_terms: list[str] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ContextBlock:
    role: str
    result: SearchResult

    def to_dict(self) -> dict[str, object]:
        return {"role": self.role, "result": self.result.to_dict()}


@dataclass(slots=True)
class ContextPack:
    query: NormalizedQuery
    results: list[SearchResult]
    context: list[ContextBlock]

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query.to_dict(),
            "results": [result.to_dict() for result in self.results],
            "context": [block.to_dict() for block in self.context],
        }


class Reranker(Protocol):
    def rerank(
        self, query: NormalizedQuery, results: list[SearchResult], *, limit: int
    ) -> list[SearchResult]: ...


@dataclass(slots=True)
class ScoreFusionReranker:
    """Fallback reranker used when no external reranker is configured."""

    def rerank(
        self, query: NormalizedQuery, results: list[SearchResult], *, limit: int
    ) -> list[SearchResult]:
        boosted = [boost_result(query, result) for result in results]
        return sorted(boosted, key=lambda item: (-item.score, item.doc_id))[:limit]


def normalize_query(raw: str) -> NormalizedQuery:
    text = " ".join(raw.strip().split())
    lowered = text.lower()
    filters: dict[str, str] = {}
    exact_terms: list[str] = []
    # A lone URL is natural language; its incidental ':' / '.' / '::' must not look like a symbol.
    if "://" in text and len(text.split()) == 1:
        return NormalizedQuery(
            raw=raw, text=text, kind="natural_language", exact_terms=[]
        )
    # A '::' query is a symbol ID; check before the path regex (`src/foo.py::Foo.run`).
    if "::" in text:
        terms = code_terms(text)
        if terms and looks_like_symbol(terms[0]):
            return NormalizedQuery(
                raw=raw, text=terms[0], kind="symbol", exact_terms=terms
            )
    if re.search(r"(^|[\s`'\"])[\w.-]+/[\w./-]+\.\w+", text):
        path = re.search(r"[\w.-]+/[\w./-]+\.\w+", text)
        term = path.group(0) if path else text
        exact_terms.append(term)
        filters["path"] = term
        return NormalizedQuery(
            raw=raw, text=term, kind="path", exact_terms=exact_terms, filters=filters
        )
    if (
        lowered.startswith("where ")
        or lowered.startswith("where is ")
        or lowered.startswith("where are ")
    ):
        return NormalizedQuery(
            raw=raw, text=text, kind="where", exact_terms=code_terms(text)
        )
    if "test" in lowered or "pytest" in lowered:
        return NormalizedQuery(
            raw=raw, text=text, kind="test", exact_terms=code_terms(text)
        )
    if "architecture" in lowered or "component" in lowered:
        return NormalizedQuery(
            raw=raw, text=text, kind="architecture", exact_terms=code_terms(text)
        )
    if "flow" in lowered or "pipeline" in lowered:
        return NormalizedQuery(
            raw=raw, text=text, kind="flow", exact_terms=code_terms(text)
        )
    terms = code_terms(text)
    if len(terms) == 1 and looks_like_symbol(terms[0]):
        return NormalizedQuery(raw=raw, text=terms[0], kind="symbol", exact_terms=terms)
    return NormalizedQuery(
        raw=raw, text=text, kind="natural_language", exact_terms=terms
    )


def looks_like_symbol(value: str) -> bool:
    if "://" in value:
        return False
    if "::" in value:
        return True
    return "." in value or "_" in value or bool(re.match(r"^[A-Z]\w+$", value))


# Namespaced symbol ID, with or without a language prefix (python:src/foo.py::Foo.run).
_NAMESPACED_ID_RE = re.compile(r"(?:[A-Za-z]+:)?[^\s:][^\s]*::[^\s]+")


def code_terms(text: str) -> list[str]:
    stripped = text.strip()
    if "::" in stripped and "://" not in stripped:
        m = _NAMESPACED_ID_RE.search(stripped)
        if m:
            return [m.group(0).rstrip(".,;!?)]}")]
    terms = re.findall(r"\b[A-Za-z_][\w.]*\b", text)
    return [term for term in terms if looks_like_symbol(term)]


def retrieve(
    repo_root: Path,
    question: str,
    *,
    top_k: int | None = None,
    expand: bool = True,
    reranker: Reranker | None = None,
) -> ContextPack:
    config = load_config(repo_root)
    retrieval = config["retrieval"] if isinstance(config["retrieval"], dict) else {}
    initial = int(retrieval.get("top_k_initial", 30))
    final = top_k or int(retrieval.get("top_k_reranked", 8))
    query = normalize_query(question)
    reranker = reranker or ScoreFusionReranker()
    candidates = initial_results(repo_root, query, limit=initial)
    ranked = reranker.rerank(query, candidates, limit=final)
    if query.kind == "symbol" and _DOTTED_RE.fullmatch(query.text):
        resolved = resolve_python_dotted(repo_root, query.text)
        if resolved is not None:
            ranked = [resolved, *(r for r in ranked if r.doc_id != resolved.doc_id)][
                :final
            ]
        elif not ranked:
            ranked = partial_suffix_results(
                repo_root, query.text, reranker, limit=initial, final=final
            )
    if query.kind == "symbol":
        ranked = [
            replace(r, resolution="exact")
            if not r.resolution and query.text in {r.symbol_id, r.doc_id}
            else r
            for r in ranked
        ]
    expand_heuristic = bool(retrieval.get("expand_heuristic_edges", True))
    context = (
        expand_context(
            repo_root, ranked, config, expand_heuristic_edges=expand_heuristic
        )
        if expand
        else []
    )
    # A doc reached again as a neighbour keeps the match label it got as a result.
    labels = {r.doc_id: r.resolution for r in ranked if r.resolution}
    for block in context:
        if not block.result.resolution and block.result.doc_id in labels:
            block.result = replace(block.result, resolution=labels[block.result.doc_id])
    return ContextPack(query=query, results=ranked, context=context)


_DOTTED_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")


_Module = tuple[str, dict[str, object]]


def _python_modules(nodes: dict[str, object]) -> dict[str, _Module]:
    """Python module name -> (graph module ID, node); ``src.``-rooted modules also answer without it."""
    modules: dict[str, _Module] = {
        name: (name, node)
        for name, node in nodes.items()
        if isinstance(node, dict)
        and node.get("kind") == "module"
        and str(node.get("path", "")).endswith((".py", ".pyi"))
    }
    for name, entry in list(modules.items()):
        if name.startswith("src.") and name[4:] not in modules:
            modules[name[4:]] = entry
    return modules


def _resolve_in_module(
    nodes: dict[str, object], modules: dict[str, _Module], parts: list[str]
) -> tuple[str | None, _Module, list[str]] | None:
    """Split *parts* at the longest module prefix; return (exact node ID or None, module, rest)."""
    for cut in range(len(parts), 0, -1):
        entry = modules.get(".".join(parts[:cut]))
        if entry is None:
            continue
        rest = parts[cut:]
        if not rest:
            return entry[0], entry, rest
        symbol_id = build_symbol_id(
            Language.PYTHON, str(entry[1]["path"]), ".".join(rest)
        )
        return (symbol_id if symbol_id in nodes else None), entry, rest
    return None


def resolve_python_dotted(repo_root: Path, dotted: str) -> SearchResult | None:
    """Exact hit for ``pkg.mod.Cls.meth`` via the longest module prefix, else one re-export hop."""
    nodes = load_graph(repo_root).get("nodes", {})
    if not isinstance(nodes, dict):
        return None
    modules = _python_modules(nodes)
    split = _resolve_in_module(nodes, modules, dotted.split("."))
    if split is None:
        return None
    found, (_, module), rest = split
    label = "module-prefix" if rest else "exact"
    if found is None:
        # One hop only: the first qualname part must be imported, not defined, here.
        bindings = module.get("bindings")
        target = bindings.get(rest[0]) if isinstance(bindings, dict) else None
        if (
            not target
            or build_symbol_id(Language.PYTHON, str(module["path"]), rest[0]) in nodes
        ):
            return None
        hop = _resolve_in_module(nodes, modules, [*str(target).split("."), *rest[1:]])
        found, label = (hop[0] if hop else None), "re-export"
    if found is None:
        return None
    hit = first_symbol_or_module(repo_root, found)
    return replace(hit, resolution=label) if hit is not None else None


def partial_suffix_results(
    repo_root: Path, dotted: str, reranker: Reranker, *, limit: int, final: int
) -> list[SearchResult]:
    """Search ever-shorter dotted suffixes; the first suffix with hits wins, labelled partial."""
    parts = dotted.split(".")
    for start in range(1, len(parts)):
        query = normalize_query(".".join(parts[start:]))
        hits = reranker.rerank(
            query, initial_results(repo_root, query, limit=limit), limit=final
        )
        if hits:
            return [replace(hit, resolution="partial-suffix") for hit in hits]
    return []


def initial_results(
    repo_root: Path, query: NormalizedQuery, *, limit: int
) -> list[SearchResult]:
    searches: list[tuple[str, dict[str, str] | None]] = [
        (query.text, query.filters or None)
    ]
    for term in query.exact_terms:
        searches.append((term, None))
    if query.kind in {"architecture", "flow"}:
        searches.append((query.text, {"doc_type": "overlay"}))
    by_id: dict[str, SearchResult] = {}
    for text, filters in searches:
        for result in search_index(repo_root, text, limit=limit, filters=filters):
            previous = by_id.get(result.doc_id)
            if previous is None or result.score > previous.score:
                by_id[result.doc_id] = result
    return list(by_id.values())


def boost_result(query: NormalizedQuery, result: SearchResult) -> SearchResult:
    boosted = replace(result)
    if query.kind == "symbol" and query.text in {
        result.symbol_id,
        result.doc_id,
        result.title,
    }:
        boosted.score += 100
    if query.kind == "path" and query.text == result.path:
        boosted.score += 90
        if result.doc_type == "module":
            boosted.score += 100
    if query.kind in {"architecture", "flow"} and result.doc_type == "overlay":
        boosted.score += 20
    if result.doc_type == "symbol":
        boosted.score += 5
    return boosted


def expand_context(
    repo_root: Path,
    results: list[SearchResult],
    config: dict[str, object],
    *,
    expand_heuristic_edges: bool = True,
) -> list[ContextBlock]:
    """Expand context via graph edges: CONFIDENT always, HEURISTIC if allowed, UNRESOLVED never."""
    retrieval = config["retrieval"] if isinstance(config["retrieval"], dict) else {}
    graph = load_graph(repo_root)
    blocks: list[ContextBlock] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        add_block(blocks, seen, "result", result)
        if result.symbol_id:
            if retrieval.get("expand_parent", True):
                add_symbol_neighbors(
                    repo_root,
                    blocks,
                    seen,
                    graph,
                    result.symbol_id,
                    "belongs_to",
                    "parent",
                    expand_heuristic_edges=expand_heuristic_edges,
                )
                add_module_context(repo_root, blocks, seen, result)
            if retrieval.get("expand_children", True):
                add_reverse_symbol_neighbors(
                    repo_root,
                    blocks,
                    seen,
                    graph,
                    result.symbol_id,
                    "belongs_to",
                    "child",
                    expand_heuristic_edges=expand_heuristic_edges,
                )
            if retrieval.get("expand_callees", True):
                add_symbol_neighbors(
                    repo_root,
                    blocks,
                    seen,
                    graph,
                    result.symbol_id,
                    "calls",
                    "callee",
                    expand_heuristic_edges=expand_heuristic_edges,
                )
            if retrieval.get("expand_callers", True):
                add_reverse_symbol_neighbors(
                    repo_root,
                    blocks,
                    seen,
                    graph,
                    result.symbol_id,
                    "calls",
                    "caller",
                    expand_heuristic_edges=expand_heuristic_edges,
                )
        if (
            result.module
            and not result.symbol_id
            and retrieval.get("expand_children", True)
        ):
            add_reverse_symbol_neighbors(
                repo_root,
                blocks,
                seen,
                graph,
                result.module,
                "defined_in",
                "module_child",
                expand_heuristic_edges=expand_heuristic_edges,
            )
    if retrieval.get("include_tests", True):
        add_test_context(repo_root, blocks, seen, results)
    add_overlay_context(repo_root, blocks, seen, results)
    return blocks[: int(retrieval.get("top_k_reranked", 8)) * 3]


def load_graph(repo_root: Path) -> dict[str, object]:
    path = repo_root / ".repo_wiki/generated/symbol_graph.json"
    if not path.exists():
        return {"nodes": {}, "edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _edge_is_allowed(edge: dict[str, str], *, expand_heuristic_edges: bool) -> bool:
    """True if the edge resolution permits traversal; no ``resolution`` key means CONFIDENT."""
    resolution = edge.get("resolution", "CONFIDENT")
    if resolution == "CONFIDENT":
        return True
    if resolution == "HEURISTIC":
        return expand_heuristic_edges
    return False


def add_symbol_neighbors(
    repo_root: Path,
    blocks: list[ContextBlock],
    seen: set[tuple[str, str]],
    graph: dict[str, object],
    symbol_id: str,
    edge_type: str,
    role: str,
    *,
    expand_heuristic_edges: bool = True,
) -> None:
    for edge in graph_edges(graph):
        if edge["source"] == symbol_id and edge["type"] == edge_type:
            if _edge_is_allowed(edge, expand_heuristic_edges=expand_heuristic_edges):
                add_first_symbol_or_module(
                    repo_root, blocks, seen, edge["target"], role
                )


def add_reverse_symbol_neighbors(
    repo_root: Path,
    blocks: list[ContextBlock],
    seen: set[tuple[str, str]],
    graph: dict[str, object],
    symbol_id: str,
    edge_type: str,
    role: str,
    *,
    expand_heuristic_edges: bool = True,
) -> None:
    for edge in graph_edges(graph):
        if edge["target"] == symbol_id and edge["type"] == edge_type:
            if _edge_is_allowed(edge, expand_heuristic_edges=expand_heuristic_edges):
                add_first_symbol_or_module(
                    repo_root, blocks, seen, edge["source"], role
                )


def graph_edges(graph: dict[str, object]) -> list[dict[str, str]]:
    edges = graph.get("edges", [])
    if not isinstance(edges, list):
        return []
    return [edge for edge in edges if isinstance(edge, dict)]


def first_symbol_or_module(repo_root: Path, identifier: str) -> SearchResult | None:
    results = search_index(
        repo_root, identifier, limit=1, filters={"symbol_id": identifier}
    )
    if not results:
        results = search_index(
            repo_root,
            identifier,
            limit=1,
            filters={"module": identifier, "doc_type": "module"},
        )
    return results[0] if results else None


def add_first_symbol_or_module(
    repo_root: Path,
    blocks: list[ContextBlock],
    seen: set[tuple[str, str]],
    identifier: str,
    role: str,
) -> None:
    result = first_symbol_or_module(repo_root, identifier)
    if result is not None:
        add_block(blocks, seen, role, result)


def add_module_context(
    repo_root: Path,
    blocks: list[ContextBlock],
    seen: set[tuple[str, str]],
    result: SearchResult,
) -> None:
    if result.module:
        docs = search_index(
            repo_root,
            result.module,
            limit=1,
            filters={"module": result.module, "doc_type": "module"},
        )
        if docs:
            add_block(blocks, seen, "module", docs[0])


def _symbol_id_terms(symbol_id: str) -> list[str]:
    """Name tokens of a symbol ID, split on ``.`` after the qualname following ``::`` (new form)."""
    if "::" in symbol_id:
        qualname = symbol_id.split("::", 1)[1]
        return [symbol_id] + re.split(r"\.|::", qualname)
    return [symbol_id] + symbol_id.split(".")


def add_test_context(
    repo_root: Path,
    blocks: list[ContextBlock],
    seen: set[tuple[str, str]],
    results: list[SearchResult],
) -> None:
    for result in results:
        name = result.symbol_id.rsplit(".", 1)[-1]
        if "::" in result.symbol_id:
            qualname = result.symbol_id.split("::", 1)[1]
            name = re.split(r"\.|::", qualname)[-1]
        terms = [name, result.symbol_id, result.module]
        for term in [item for item in terms if item]:
            for match in search_index(
                repo_root, term, limit=2, filters={"doc_type": "module"}
            ):
                if "test" in match.path:
                    add_block(blocks, seen, "test", match)


def add_overlay_context(
    repo_root: Path,
    blocks: list[ContextBlock],
    seen: set[tuple[str, str]],
    results: list[SearchResult],
) -> None:
    for result in results:
        terms = [result.module, result.title]
        terms.extend(_symbol_id_terms(result.symbol_id))
        for term in terms:
            if not term:
                continue
            for match in search_index(
                repo_root, term, limit=2, filters={"doc_type": "overlay"}
            ):
                add_block(blocks, seen, "overlay", match)


def add_block(
    blocks: list[ContextBlock],
    seen: set[tuple[str, str]],
    role: str,
    result: SearchResult,
) -> None:
    key = (role, result.doc_id)
    if key not in seen:
        blocks.append(ContextBlock(role=role, result=result))
        seen.add(key)
