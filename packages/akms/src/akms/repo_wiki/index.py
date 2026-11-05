"""Local SQLite-backed document index.

**Erasure.** The connection runs with ``PRAGMA secure_delete=ON`` and the FTS5
table with its ``secure-delete`` option, so a removed or replaced document's
text is overwritten rather than left in free space. Where the SQLite library
predates FTS5 ``secure-delete`` (3.42), a write that removed text also runs the
FTS5 ``optimize`` command and ``VACUUM``. A database in WAL mode is
checkpointed with ``TRUNCATE`` after such a write; the index itself uses the
default rollback journal, which SQLite removes at commit.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from akms.repo_wiki.config import effective_excludes, init_repo_wiki, load_config
from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.paths import ensure_parent, repo_relative
from akms.repo_wiki.render_markdown import repo_commit
from akms.repo_wiki.scanner import is_excluded, read_gitignore
from akms.repo_wiki.simple_yaml import load_yaml

INDEX_PATH = ".repo_wiki/index/repo_wiki.sqlite3"


@dataclass(slots=True)
class IndexDocument:
    doc_id: str
    doc_type: str
    path: str
    content: str
    module: str = ""
    symbol_id: str = ""
    kind: str = ""
    start_line: int = 0
    end_line: int = 0
    repo_commit: str = "unknown"
    content_hash: str = ""
    title: str = ""

    def metadata(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("content")
        return data


@dataclass(slots=True)
class SearchResult:
    doc_id: str
    doc_type: str
    path: str
    content: str
    score: float
    module: str = ""
    symbol_id: str = ""
    kind: str = ""
    start_line: int = 0
    end_line: int = 0
    repo_commit: str = "unknown"
    content_hash: str = ""
    title: str = ""
    # How a symbol query reached this hit: exact | module-prefix | re-export | partial-suffix.
    resolution: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class IndexSummary:
    indexed: int = 0
    skipped_unchanged: int = 0
    deleted: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class VectorBackend(Protocol):
    """Optional extension point for vector indexes."""

    def search(self, query: str, *, limit: int) -> list[SearchResult]: ...


class IndexBackend(Protocol):
    def index_documents(
        self, documents: list[IndexDocument], *, changed_only: bool = False
    ) -> IndexSummary: ...

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: dict[str, str] | None = None,
    ) -> list[SearchResult]: ...


class SQLiteIndexBackend:
    def __init__(self, path: Path) -> None:
        self.path = path
        ensure_parent(path)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        # Overwrite deleted content instead of leaving it in free pages.
        self.connection.execute("PRAGMA secure_delete=ON")
        self._init_schema()
        self.fts_secure_delete = self._enable_fts_secure_delete()

    def close(self) -> None:
        self.connection.close()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
              doc_id TEXT PRIMARY KEY,
              doc_type TEXT NOT NULL,
              path TEXT NOT NULL,
              module TEXT NOT NULL DEFAULT '',
              symbol_id TEXT NOT NULL DEFAULT '',
              kind TEXT NOT NULL DEFAULT '',
              start_line INTEGER NOT NULL DEFAULT 0,
              end_line INTEGER NOT NULL DEFAULT 0,
              repo_commit TEXT NOT NULL DEFAULT 'unknown',
              content_hash TEXT NOT NULL,
              title TEXT NOT NULL DEFAULT '',
              content TEXT NOT NULL,
              metadata_json TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
              USING fts5(doc_id UNINDEXED, title, path, module, symbol_id, content);
            """
        )
        self.connection.commit()

    def _enable_fts_secure_delete(self) -> bool:
        """Turn on FTS5 ``secure-delete``; ``False`` where SQLite lacks it (< 3.42)."""
        row = self.connection.execute(
            "SELECT v FROM documents_fts_config WHERE k = 'secure-delete'"
        ).fetchone()
        if row is not None and str(row[0]) == "1":
            return True
        try:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO documents_fts(documents_fts, rank) "
                    "VALUES('secure-delete', 1)"
                )
        except sqlite3.OperationalError:
            return False
        return True

    def _erase_removed_text(self) -> None:
        """Run after a committed write that deleted or replaced documents."""
        if not self.fts_secure_delete:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO documents_fts(documents_fts) VALUES('optimize')"
                )
            self.connection.execute("VACUUM")
        mode = self.connection.execute("PRAGMA journal_mode").fetchone()[0]
        if str(mode).lower() == "wal":
            self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def index_documents(
        self, documents: list[IndexDocument], *, changed_only: bool = False
    ) -> IndexSummary:
        summary = IndexSummary()
        incoming_ids = {doc.doc_id for doc in documents}
        with self.connection:
            existing = {
                str(row["doc_id"]): str(row["content_hash"])
                for row in self.connection.execute(
                    "SELECT doc_id, content_hash FROM documents"
                )
            }
            replaced = 0
            for doc in documents:
                if changed_only and existing.get(doc.doc_id) == doc.content_hash:
                    summary.skipped_unchanged += 1
                    continue
                if doc.doc_id in existing:
                    replaced += 1
                self._upsert_document(doc)
                summary.indexed += 1
            for doc_id in sorted(set(existing) - incoming_ids):
                self._delete_document(doc_id)
                summary.deleted += 1
        if replaced or summary.deleted:
            self._erase_removed_text()
        return summary

    def _upsert_document(self, doc: IndexDocument) -> None:
        self.connection.execute(
            "DELETE FROM documents_fts WHERE doc_id = ?", (doc.doc_id,)
        )
        self.connection.execute(
            """
            INSERT INTO documents (
              doc_id, doc_type, path, module, symbol_id, kind, start_line, end_line,
              repo_commit, content_hash, title, content, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
              doc_type=excluded.doc_type,
              path=excluded.path,
              module=excluded.module,
              symbol_id=excluded.symbol_id,
              kind=excluded.kind,
              start_line=excluded.start_line,
              end_line=excluded.end_line,
              repo_commit=excluded.repo_commit,
              content_hash=excluded.content_hash,
              title=excluded.title,
              content=excluded.content,
              metadata_json=excluded.metadata_json
            """,
            (
                doc.doc_id,
                doc.doc_type,
                doc.path,
                doc.module,
                doc.symbol_id,
                doc.kind,
                doc.start_line,
                doc.end_line,
                doc.repo_commit,
                doc.content_hash,
                doc.title,
                doc.content,
                json.dumps(doc.metadata(), sort_keys=True),
            ),
        )
        self.connection.execute(
            """
            INSERT INTO documents_fts (doc_id, title, path, module, symbol_id, content)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doc.doc_id, doc.title, doc.path, doc.module, doc.symbol_id, doc.content),
        )

    def _delete_document(self, doc_id: str) -> None:
        self.connection.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        self.connection.execute("DELETE FROM documents_fts WHERE doc_id = ?", (doc_id,))

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        clauses, params = filter_clauses(filters)
        exact_rows = self._exact_rows(query, clauses, params)
        fts_rows = self._fts_rows(query, clauses, params)
        scored: dict[str, SearchResult] = {}
        for row, score in exact_rows + fts_rows:
            result = row_to_result(row, score)
            previous = scored.get(result.doc_id)
            if previous is None or result.score > previous.score:
                scored[result.doc_id] = result
        return sorted(scored.values(), key=lambda item: (-item.score, item.doc_id))[
            :limit
        ]

    def _exact_rows(
        self, query: str, clauses: list[str], params: list[str]
    ) -> list[tuple[sqlite3.Row, float]]:
        like = f"%{query}%"
        exact = query.strip()
        where = [
            "(doc_id = ? OR symbol_id = ? OR path = ? OR module = ? OR title = ?)",
            "(doc_id LIKE ? OR symbol_id LIKE ? OR path LIKE ? OR module LIKE ? OR title LIKE ?)",
        ]
        sql = "SELECT * FROM documents WHERE (" + " OR ".join(where) + ")"
        sql_params: list[str] = [
            exact,
            exact,
            exact,
            exact,
            exact,
            like,
            like,
            like,
            like,
            like,
        ]
        if clauses:
            sql += " AND " + " AND ".join(clauses)
            sql_params.extend(params)
        rows = self.connection.execute(sql, sql_params).fetchall()
        scored: list[tuple[sqlite3.Row, float]] = []
        for row in rows:
            score = (
                100.0
                if exact
                in {row["doc_id"], row["symbol_id"], row["path"], row["module"]}
                else 60.0
            )
            scored.append((row, score))
        return scored

    def _fts_rows(
        self, query: str, clauses: list[str], params: list[str]
    ) -> list[tuple[sqlite3.Row, float]]:
        match = fts_query(query)
        if not match:
            return []
        sql = """
            SELECT documents.*, bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents ON documents.doc_id = documents_fts.doc_id
            WHERE documents_fts MATCH ?
        """
        sql_params: list[str] = [match]
        if clauses:
            sql += " AND " + " AND ".join(f"documents.{clause}" for clause in clauses)
            sql_params.extend(params)
        rows = self.connection.execute(sql, sql_params).fetchall()
        return [(row, 20.0 + (-float(row["rank"]))) for row in rows]


def filter_clauses(filters: dict[str, str] | None) -> tuple[list[str], list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    for key, value in sorted((filters or {}).items()):
        if key not in {"doc_type", "path", "module", "symbol_id", "kind"}:
            continue
        clauses.append(f"{key} = ?")
        params.append(value)
    return clauses, params


def fts_query(query: str) -> str:
    tokens = re.findall(r"[\w./:-]+", query, flags=re.UNICODE)
    phrase = " ".join(tokens)
    quoted = [quote_fts_value(token) for token in tokens]
    if " " in phrase:
        quoted.insert(0, quote_fts_value(phrase))
    return " OR ".join(dict.fromkeys(quoted))


def quote_fts_value(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) + chr(34))}"'


def row_to_result(row: sqlite3.Row, score: float) -> SearchResult:
    return SearchResult(
        doc_id=str(row["doc_id"]),
        doc_type=str(row["doc_type"]),
        path=str(row["path"]),
        content=str(row["content"]),
        score=score,
        module=str(row["module"]),
        symbol_id=str(row["symbol_id"]),
        kind=str(row["kind"]),
        start_line=int(row["start_line"]),
        end_line=int(row["end_line"]),
        repo_commit=str(row["repo_commit"]),
        content_hash=str(row["content_hash"]),
        title=str(row["title"]),
    )


def update_index(
    repo_root: Path, *, changed_only: bool = False, force: bool = False
) -> IndexSummary:
    init_repo_wiki(repo_root)
    docs = discover_index_documents(repo_root)
    backend = SQLiteIndexBackend(repo_root / INDEX_PATH)
    try:
        return backend.index_documents(docs, changed_only=changed_only and not force)
    finally:
        backend.close()


def search_index(
    repo_root: Path,
    query: str,
    *,
    limit: int = 10,
    filters: dict[str, str] | None = None,
) -> list[SearchResult]:
    backend = SQLiteIndexBackend(repo_root / INDEX_PATH)
    try:
        return backend.search(query, limit=limit, filters=filters)
    finally:
        backend.close()


def discover_index_documents(repo_root: Path) -> list[IndexDocument]:
    root = repo_root.resolve()
    config = load_config(root)
    generated = root / str(config["generation"]["output_dir"])  # type: ignore[index]
    overlays = root / ".repo_wiki" / "overlays"
    docs: list[IndexDocument] = []
    for path in sorted(generated.rglob("*.md")) if generated.exists() else []:
        rel = repo_relative(path, root)
        parsed = document_from_markdown(root, path, rel, human_authored=False)
        if parsed and not source_is_excluded(parsed.path, root, config):
            docs.append(parsed)
    for path in sorted(overlays.rglob("*.md")) if overlays.exists() else []:
        rel = repo_relative(path, root)
        # Overlays live under .repo_wiki/, so the tool-state set must not apply.
        if source_is_excluded(rel, root, config, tool_state=False):
            continue
        parsed = document_from_markdown(root, path, rel, human_authored=True)
        if parsed:
            docs.append(parsed)
    return docs


def source_is_excluded(
    path: str, repo_root: Path, config: dict[str, object], *, tool_state: bool = True
) -> bool:
    scanner = config["scanner"] if isinstance(config["scanner"], dict) else {}
    gitignore_patterns = (
        read_gitignore(repo_root) if scanner.get("respect_gitignore", True) else []
    )
    return is_excluded(
        path, effective_excludes(config, tool_state=tool_state), gitignore_patterns
    )


def document_from_markdown(
    repo_root: Path, path: Path, rel_path: str, *, human_authored: bool
) -> IndexDocument | None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    metadata, body = split_frontmatter(raw)
    doc_type = str(
        metadata.get("doc_type") or ("overlay" if human_authored else "document")
    )
    title = first_heading(body) or Path(rel_path).stem
    symbol_id = str(metadata.get("symbol_id") or "")
    module = str(metadata.get("module") or "")
    kind = str(metadata.get("kind") or "")
    source_path = str(metadata.get("path") or rel_path)
    doc_id = document_id_for(doc_type, rel_path, module, symbol_id, human_authored)
    return IndexDocument(
        doc_id=doc_id,
        doc_type=doc_type,
        path=source_path,
        content=body,
        module=module,
        symbol_id=symbol_id,
        kind=kind,
        start_line=int_value(metadata.get("start_line")),
        end_line=int_value(metadata.get("end_line")),
        repo_commit=str(metadata.get("repo_commit") or repo_commit(repo_root)),
        content_hash=sha256_text(raw),
        title=title,
    )


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    metadata = load_yaml(text[4:end])
    return metadata, text[end + 4 :].lstrip()


def document_id_for(
    doc_type: str, rel_path: str, module: str, symbol_id: str, human_authored: bool
) -> str:
    if doc_type == "symbol" and symbol_id:
        return symbol_id
    if doc_type == "summary" and symbol_id:
        return f"summary:{symbol_id}"
    if doc_type == "module" and module:
        return module
    if human_authored:
        return f"overlay:{rel_path}"
    return rel_path


def first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def int_value(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0
