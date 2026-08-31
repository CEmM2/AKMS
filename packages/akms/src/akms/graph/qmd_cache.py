"""qmd_cache.py — QMD query cache layer (§2.6 of system design).

Caches qmd search results by (graph_version, query_hash).
Cache is invalidated when graph_version changes.

Graph version = SHA256 of graph.json contents.
Query hash = SHA256 of (tags, role, depth) — see query_subgraph.compute_query_hash.

Cache storage: <repo>/knowledge/graph/.qmd_cache/
Each entry: {graph_version}_{query_hash}.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_graph_version(graph_json_path: str | Path) -> str:
    """Compute SHA256 hash of graph.json as the graph version.

    Args:
        graph_json_path: Path to graph.json.

    Returns:
        SHA256 hex digest of the file contents.
    """
    path = Path(graph_json_path)
    if not path.exists():
        return "no-graph"

    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def _cache_dir(repo_root: str | Path) -> Path:
    """Resolve the cache directory path."""
    return Path(repo_root) / "knowledge" / "graph" / ".qmd_cache"


def _cache_key(graph_version: str, query_hash: str) -> str:
    """Build the cache file name."""
    return f"{graph_version[:16]}_{query_hash[:16]}.json"


def get_cached(
    repo_root: str | Path,
    graph_version: str,
    query_hash: str,
) -> list | None:
    """Retrieve cached query results if available.

    Args:
        repo_root: Repository root path.
        graph_version: SHA256 of current graph.json.
        query_hash: SHA256 of query parameters.

    Returns:
        Cached result list, or None on cache miss.
    """
    cache = _cache_dir(repo_root)
    key = _cache_key(graph_version, query_hash)
    cache_file = cache / key

    if not cache_file.exists():
        return None

    try:
        with open(cache_file) as f:
            data = json.load(f)

        # Validate the stored graph version matches
        if data.get("graph_version") != graph_version:
            logger.info("Cache version mismatch, invalidating %s", key)
            cache_file.unlink(missing_ok=True)
            return None

        logger.info("Cache hit: %s", key)
        return data.get("results")
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Cache read error for %s: %s", key, e)
        cache_file.unlink(missing_ok=True)
        return None


def put_cached(
    repo_root: str | Path,
    graph_version: str,
    query_hash: str,
    results: list,
) -> Path:
    """Store query results in cache.

    Args:
        repo_root: Repository root path.
        graph_version: SHA256 of current graph.json.
        query_hash: SHA256 of query parameters.
        results: The query results to cache (list of node_id strings).

    Returns:
        Path to the cache file.
    """
    cache = _cache_dir(repo_root)
    cache.mkdir(parents=True, exist_ok=True)

    key = _cache_key(graph_version, query_hash)
    cache_file = cache / key

    data = {
        "graph_version": graph_version,
        "query_hash": query_hash,
        "results": results,
    }

    with open(cache_file, "w") as f:
        json.dump(data, f, sort_keys=True, indent=2)

    logger.info("Cache put: %s (%d results)", key, len(results))
    return cache_file


def invalidate_cache(repo_root: str | Path) -> int:
    """Remove all cached entries.

    Called when graph.json is rebuilt to avoid stale results.

    Returns:
        Number of cache files removed.
    """
    cache = _cache_dir(repo_root)
    if not cache.exists():
        return 0

    count = 0
    for f in cache.glob("*.json"):
        f.unlink()
        count += 1

    logger.info("Invalidated %d cache entries", count)
    return count


def is_qmd_available() -> bool:
    """Check if qmd CLI is installed and accessible."""
    return shutil.which("qmd") is not None
