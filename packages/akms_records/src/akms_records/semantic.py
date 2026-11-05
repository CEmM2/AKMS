"""Optional vector search through the external ``qmd`` tool.

``recall --semantic`` adds nearest-neighbour search over local embeddings. It is off
by default and adds no Python dependency: it runs ``qmd``, a separate command-line
tool, and raises a typed error when the tool or its embedding model is missing.

**One index per store root.** The index lives in ``<store>/.index/semantic/``, beside
the full-text index and, like it, holding every scope of that root. Git ignores it and
it can be deleted at any time, since everything in it is derived. qmd gets a private
database, configuration folder and cache folder through its environment, so the user's
own qmd index and settings are neither read nor written.

**No LLM, no network.** A search runs ``qmd query 'vec: ...' --no-rerank``, which only
embeds the query. Plain ``qmd vsearch`` and ``qmd query`` are not used, because both
run a text-generating model to expand the query, and they download any model they
lack. qmd is given the embedding model as a local file path, so it has nothing to
download, and paths that do not exist in place of the other two models, so loading
one fails instead of downloading it.

**Erasure.** qmd keeps text in its database after a document goes away, so this module
never deletes one document: :func:`drop_index` removes the whole folder, and the next
semantic recall builds it again from the records that remain. Anything that takes a
document out of the index (an erasure, or a record that became sensitive) goes the
same way. :class:`~akms_records.store.RecordStore` calls this from ``erase``.

**What is embedded.** The text the full-text index holds: summary, tags and the
schema's search text. Sensitive records are left out unless ``embed_sensitive`` is
passed, and they leave again the first time it is not.

qmd only supplies an order of record IDs. :func:`akms_records.query.recall` reads the
records from its own index under its own filters, so a hit here can never show
something recall would otherwise refuse.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from akms_records.errors import RecordsError
from akms_records.fsio import FILE_MODE, replace_file
from akms_records.index import INDEX_DIRNAME
from akms_records.procs import pid_alive

if TYPE_CHECKING:
    from akms_records.store import RecordStore

__all__ = [
    "MODEL_ENV",
    "SEMANTIC_DIRNAME",
    "drop_index",
    "holds_any",
    "nearest",
]

SEMANTIC_DIRNAME = "semantic"
MODEL_ENV = "AKMS_RECORDS_QMD_MODEL"
MODEL_FILE = "hf_ggml-org_embeddinggemma-300M-Q8_0.gguf"
MANIFEST = "manifest.json"
MANIFEST_FORMAT = 1
LOCK_NAME = "semantic.lock"
COLLECTION = "records"
DIR_MODE = 0o700
BUILD_TIMEOUT = 3600.0
QUERY_TIMEOUT = 300.0
BUILD_WAIT = 3600.0  # a recall waits this long for another process's build
ERASE_WAIT = 60.0  # an erasure waits this long, then reports the index not reached
_ERROR_CHARS = 500
_HIT_RE = re.compile(r"\Aqmd://" + COLLECTION + r"/([0-9a-f]{32})\.md\Z")
_NOT_A_MODEL = "does-not-exist.gguf"


def _folder(root: Path) -> Path:
    return root / INDEX_DIRNAME / SEMANTIC_DIRNAME


def _stem(record_id: str) -> str:
    """A file name for a record: qmd rewrites names, and hex comes through unchanged."""
    return hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:32]


# ------------------------------------------------------------------ the lock
class _LockBusy(Exception):
    pass


@contextmanager
def _lock(root: Path, *, wait: float) -> Iterator[None]:
    """One build or erasure at a time. A lock whose process is gone is removed."""
    directory = root / INDEX_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOCK_NAME
    deadline = time.monotonic() + wait
    while True:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        except FileExistsError:
            try:
                owner = int(path.read_text(encoding="ascii").strip() or "0")
            except (OSError, ValueError):
                owner = 0
            if owner and not pid_alive(owner):
                path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise _LockBusy(str(path)) from None
            time.sleep(0.1)
            continue
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        break
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


# ------------------------------------------------------------------ erasure
def drop_index(root: Path, *, wait: float = ERASE_WAIT) -> str:
    """Delete a store's semantic index: ``absent``, ``deleted`` or ``not_reached``.

    Call this after the record has left the full-text index. A build reads its text
    from there while holding the lock, so a build that started earlier finishes
    first, and one that starts later cannot see the record.
    """
    if not (root / INDEX_DIRNAME).is_dir():
        return "absent"
    try:
        with _lock(root, wait=wait):
            folder = _folder(root)
            if not folder.exists():
                return "absent"
            shutil.rmtree(folder)
    except (_LockBusy, OSError):
        return "not_reached"
    return "deleted"


def holds_any(root: Path, record_ids: Sequence[str]) -> bool:
    """Whether the index on disk was built with any of these records."""
    stems = _read_manifest(_folder(root)).get("documents", {})
    return any(_stem(record_id) in stems for record_id in record_ids)


# ------------------------------------------------------------ running the tool
def _failed(message: str, code: str = "semantic_failed") -> RecordsError:
    return RecordsError(message, code=code)


def _qmd_command() -> list[str]:
    path = shutil.which("qmd")
    if path is None:
        raise _failed(
            "recall --semantic needs the qmd tool, which was not found on PATH; "
            "plain recall needs nothing extra",
            "qmd_missing",
        )
    return [path]


def _model_path() -> Path:
    """The embedding model as a local file: qmd cannot download what it is handed."""
    configured = os.environ.get(MODEL_ENV)
    if configured:
        path = Path(configured)
    else:
        cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        path = Path(cache) / "qmd" / "models" / MODEL_FILE
    if not path.is_file():
        raise _failed(
            f"recall --semantic needs qmd's embedding model at {path}. Nothing is "
            f"downloaded at search time: run qmd once to fetch it, or set {MODEL_ENV} "
            "to a local model file",
            "semantic_model_missing",
        )
    return path


def _environment(folder: Path, model: Path) -> dict[str, str]:
    """Keep qmd inside ``folder``. The XDG folders are a second guard for the index."""
    env = dict(os.environ)
    env.pop("CI", None)
    env.update(
        INDEX_PATH=str(folder / "qmd.sqlite"),
        QMD_CONFIG_DIR=str(folder / "config"),
        XDG_CONFIG_HOME=str(folder / "config"),
        XDG_CACHE_HOME=str(folder / "cache"),
        QMD_EMBED_MODEL=str(model),
        QMD_GENERATE_MODEL=str(folder / _NOT_A_MODEL),
        QMD_RERANK_MODEL=str(folder / _NOT_A_MODEL),
        NO_COLOR="1",
    )
    return env


def _run(
    command: list[str], folder: Path, model: Path, *arguments: str, timeout: float
) -> str:
    import subprocess

    try:
        done = subprocess.run(
            [*command, *arguments],
            cwd=folder,
            env=_environment(folder, model),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise _failed(f"qmd {arguments[0]} took over {timeout:.0f} s") from None
    except OSError as exc:
        raise _failed(f"qmd {arguments[0]} could not run: {exc}") from None
    if done.returncode != 0:
        tail = done.stderr.strip()[-_ERROR_CHARS:]
        raise _failed(f"qmd {arguments[0]} failed ({done.returncode}): {tail}")
    return done.stdout


# -------------------------------------------------------------- the index
def _read_manifest(folder: Path) -> dict[str, Any]:
    try:
        value = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _documents(store: RecordStore, *, embed_sensitive: bool) -> dict[str, str]:
    """The text to index for each file stem, from the full-text index of this root."""
    index = store.index_for_read()
    if index is None:
        return {}
    rows = index.db.execute(
        "SELECT r.record_id, r.sensitivity, f.summary, f.tags, f.text "
        "FROM records r JOIN records_fts f ON f.rowid = r.rid"
    ).fetchall()
    documents = {}
    for record_id, sensitivity, summary, tags, text in rows:
        if sensitivity == "sensitive" and not embed_sensitive:
            continue
        # qmd embeds the first heading as a title; without one, the file name would be.
        heading = " ".join(str(summary or "").split())[:120]
        documents[_stem(record_id)] = (
            f"# {heading}\n\n{summary or ''}\n\n{tags or ''}\n\n{text or ''}\n"
        )
    return documents


def _write_document(path: Path, text: str) -> None:
    """Written plainly: the index is derived, so this needs no durability."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sync(
    store: RecordStore, command: list[str], model: Path, *, embed_sensitive: bool
) -> dict[str, str]:
    """Bring the index up to the store's records; return the record ID per stem.

    Added or changed records go in incrementally. A record that left means delete
    and rebuild, since qmd would keep its text.
    """
    folder = _folder(store.root)
    documents = _documents(store, embed_sensitive=embed_sensitive)
    digests = {stem: _digest(text) for stem, text in documents.items()}
    model_id = f"{model.name}:{model.stat().st_size}"
    manifest = _read_manifest(folder)
    built = manifest.get("documents")
    if (
        manifest.get("format") != MANIFEST_FORMAT
        or manifest.get("model") != model_id
        or not isinstance(built, dict)
        or set(built) - set(digests)
    ):
        if folder.exists():
            shutil.rmtree(folder)
        built = {}
    changed = [stem for stem in digests if built.get(stem) != digests[stem]]
    if changed:
        new_index = not built
        docs = folder / "docs"
        docs.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
        folder.chmod(DIR_MODE)
        for stem in changed:
            _write_document(docs / f"{stem}.md", documents[stem])
        if new_index:
            _run(
                command,
                folder,
                model,
                "collection",
                "add",
                str(docs),
                "--name",
                COLLECTION,
                "--mask",
                "*.md",
                timeout=BUILD_TIMEOUT,
            )
        else:
            _run(command, folder, model, "update", timeout=BUILD_TIMEOUT)
        _run(command, folder, model, "embed", timeout=BUILD_TIMEOUT)
        for path in folder.iterdir():
            if path.is_file():
                path.chmod(FILE_MODE)
        replace_file(
            folder / MANIFEST,
            json.dumps(
                {"format": MANIFEST_FORMAT, "model": model_id, "documents": digests},
                sort_keys=True,
            ).encode("utf-8"),
        )
    index = store.index_for_read()
    if index is None:
        return {}
    return {
        _stem(row[0]): row[0]
        for row in index.db.execute("SELECT record_id FROM records")
    }


def _vector_query(text: str) -> str:
    """One line qmd accepts: it rejects quotes it cannot balance and any ``-word``."""
    return " ".join(re.sub(r'["\-]+', " ", text).split())


def nearest(
    store: RecordStore, query: str, *, limit: int, embed_sensitive: bool = False
) -> list[str]:
    """Record IDs nearest to ``query``, best first, after updating the index."""
    command = _qmd_command()
    model = _model_path()
    text = _vector_query(query)
    try:
        with _lock(store.root, wait=BUILD_WAIT):
            ids = _sync(store, command, model, embed_sensitive=embed_sensitive)
    except _LockBusy as exc:
        raise _failed(f"another process holds {exc}", "semantic_locked") from None
    folder = _folder(store.root)
    if not text or not ids or not (folder / "qmd.sqlite").is_file():
        return []
    output = _run(
        command,
        folder,
        model,
        "query",
        f"vec: {text}",
        "--no-rerank",
        "--json",
        "-n",
        str(limit),
        timeout=QUERY_TIMEOUT,
    )
    try:
        results = json.loads(output)
    except ValueError:
        raise _failed("qmd query did not print JSON") from None
    if not isinstance(results, list):
        raise _failed("qmd query did not print a list")
    ordered: dict[str, None] = {}
    for result in results:
        found = (
            _HIT_RE.match(str(result.get("file"))) if isinstance(result, dict) else None
        )
        if found and found.group(1) in ids:
            ordered[ids[found.group(1)]] = None
    return list(ordered)
