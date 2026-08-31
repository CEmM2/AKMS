"""Tests for qmd_cache.py — Phase 3 Task 3.2.

Tests:
  - Cache put/get round-trip
  - Graph version mismatch invalidation
  - Full cache invalidation
  - Graph version computation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms.graph.qmd_cache import (
    compute_graph_version,
    get_cached,
    invalidate_cache,
    put_cached,
)


class TestCacheRoundTrip:
    """Basic cache put → get."""

    def test_put_and_get(self, tmp_path):
        """Stored results are retrievable."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "knowledge" / "graph").mkdir(parents=True)

        results = ["n1", "n2", "n3"]
        put_cached(repo, "graph-v1", "query-h1", results)

        cached = get_cached(repo, "graph-v1", "query-h1")
        assert cached == results

    def test_cache_miss(self, tmp_path):
        """Non-existent cache entry returns None."""
        repo = tmp_path / "repo"
        repo.mkdir()
        cached = get_cached(repo, "graph-v1", "nonexistent")
        assert cached is None

    def test_version_mismatch_invalidates(self, tmp_path):
        """Cached entry with different graph version returns None."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "knowledge" / "graph").mkdir(parents=True)

        put_cached(repo, "graph-v1", "query-h1", ["n1"])
        # Read with different version
        cached = get_cached(repo, "graph-v2", "query-h1")
        assert cached is None


class TestCacheInvalidation:
    """Full cache clear."""

    def test_invalidate_clears_all(self, tmp_path):
        """invalidate_cache removes all entries."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "knowledge" / "graph").mkdir(parents=True)

        put_cached(repo, "v1", "h1", ["a"])
        put_cached(repo, "v1", "h2", ["b"])
        put_cached(repo, "v1", "h3", ["c"])

        count = invalidate_cache(repo)
        assert count == 3

        # All gone
        assert get_cached(repo, "v1", "h1") is None
        assert get_cached(repo, "v1", "h2") is None

    def test_invalidate_empty_cache(self, tmp_path):
        """Invalidating non-existent cache returns 0."""
        repo = tmp_path / "repo"
        repo.mkdir()
        count = invalidate_cache(repo)
        assert count == 0


class TestGraphVersion:
    """Graph version SHA256 computation."""

    def test_compute_from_file(self, tmp_path):
        """SHA256 of graph.json contents."""
        graph_file = tmp_path / "graph.json"
        graph_file.write_text(json.dumps({"nodes": [], "links": []}))

        version = compute_graph_version(graph_file)
        assert len(version) == 64  # SHA256 hex length
        assert version.isalnum()

    def test_missing_file(self, tmp_path):
        """Missing file returns sentinel."""
        version = compute_graph_version(tmp_path / "nonexistent.json")
        assert version == "no-graph"

    def test_deterministic(self, tmp_path):
        """Same content → same hash."""
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        content = json.dumps({"nodes": [{"id": "n1"}]})
        f1.write_text(content)
        f2.write_text(content)

        assert compute_graph_version(f1) == compute_graph_version(f2)

    def test_different_content(self, tmp_path):
        """Different content → different hash."""
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text(json.dumps({"nodes": [{"id": "n1"}]}))
        f2.write_text(json.dumps({"nodes": [{"id": "n2"}]}))

        assert compute_graph_version(f1) != compute_graph_version(f2)
