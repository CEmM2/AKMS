"""Package-level tests for Request normalization and stable hash.

Covers the specification (the internal plan) acceptance criteria:

1. Same input → same hash across two invocations (and across sessions).
2. Adding a UI-only key does not change the hash.
3. Reordering ``seed_tags`` / ``exporters`` does not change the hash.
4. Missing optional fields receive documented defaults.
5. All 11 normalized fields are recognized.

Plus a bonus regression test confirming ``topic`` is case-sensitive (only
enum-like fields are lowercased) to protect against accidental
over-normalization.
"""

from __future__ import annotations

import pytest

from akms_learn import (
    LearningRequest,
    normalize_request,
    request_hash,
    to_canonical_dict,
)
from akms_learn.requests import NORMALIZED_FIELDS


# Pinned digest of the canonical form of FIXTURE_REQUEST below. If the
# canonical form ever changes byte-for-byte, this constant will need to be
# regenerated AND the change must be deliberate (it breaks every packet
# whose request_hash has been recorded).
PINNED_HASH = "b9b9639c5e0295e43d76662ff2e663a1613e26fd14e5f57a3d8dc2d50385f15a"

FIXTURE_REQUEST: dict = {
    "topic": "j² return mapping",  # non-ASCII to exercise ensure_ascii=False
    "goal": "Understand the radial return algorithm",
    "audience": "Engineer",
    "depth": "Implementation",
    "generation_option": "deterministic_outline",
    "seed_tags": ["plasticity", "j2", "return-mapping"],
    "max_nodes": 25,
    "max_depth": 3,
    "include_pitfalls": True,
    "include_code_links": True,
    "exporters": ["markdown", "bundle"],
}


class TestRequestHash:
    """Tests for Request normalization and stable hash."""

    @pytest.mark.unit
    def test_request_hash_stable(self):
        """Same input yields same hash across two invocations + pinned digest."""
        n1 = normalize_request(FIXTURE_REQUEST)
        n2 = normalize_request(FIXTURE_REQUEST)
        assert n1 == n2
        assert request_hash(n1) == request_hash(n2)

        # Pinned digest — catches any drift in canonical form across sessions.
        assert request_hash(n1) == PINNED_HASH

        # Hash is a 64-char lowercase hex SHA-256 digest.
        assert len(request_hash(n1)) == 64
        assert all(c in "0123456789abcdef" for c in request_hash(n1))

    @pytest.mark.unit
    def test_request_hash_ignores_ui_state(self):
        """Adding Logic-Loom UI-only keys does not change the hash."""
        base = dict(FIXTURE_REQUEST)
        polluted = dict(FIXTURE_REQUEST)
        polluted.update(
            preview_mode="dark",
            ui_theme="solarized",
            session_id="abc-123",
            extra_topic="ignored",
        )

        assert request_hash(normalize_request(base)) == request_hash(
            normalize_request(polluted)
        )
        # The polluted-normalized dict has exactly the 11 known keys.
        assert set(normalize_request(polluted).keys()) == set(NORMALIZED_FIELDS)

    @pytest.mark.unit
    def test_request_hash_seed_tags_order_invariant(self):
        """Reordering seed_tags or exporters does not change the hash."""
        a = dict(
            FIXTURE_REQUEST, seed_tags=["b", "a", "c"], exporters=["markdown", "bundle"]
        )
        b = dict(
            FIXTURE_REQUEST, seed_tags=["c", "a", "b"], exporters=["bundle", "markdown"]
        )
        assert request_hash(normalize_request(a)) == request_hash(normalize_request(b))

        # Sanity: the canonical form actually sorted them.
        canon = normalize_request(a)
        assert canon["seed_tags"] == ["a", "b", "c"]
        assert canon["exporters"] == ["bundle", "markdown"]

    @pytest.mark.unit
    def test_normalize_defaults(self):
        """Missing optional fields receive documented defaults."""
        minimal = {
            "topic": "t",
            "goal": "g",
            "generation_option": "deterministic_outline",
        }
        canon = normalize_request(minimal)

        # Exactly the 11 fields appear.
        assert set(canon.keys()) == set(NORMALIZED_FIELDS)
        assert len(canon) == 11

        # Documented defaults from requests.py.
        assert canon["topic"] == "t"
        assert canon["goal"] == "g"
        assert canon["audience"] == "engineer"
        assert canon["depth"] == "implementation"
        assert canon["generation_option"] == "deterministic_outline"
        assert canon["seed_tags"] == []
        assert canon["max_nodes"] is None
        assert canon["max_depth"] is None
        assert canon["include_pitfalls"] is True
        assert canon["include_code_links"] is True
        assert canon["exporters"] == []

    @pytest.mark.unit
    def test_request_hash_topic_case_preserved(self):
        """Bonus: topic is case-sensitive — only enum-like fields are lowercased."""
        upper = dict(FIXTURE_REQUEST, topic="J2 Return Mapping")
        lower = dict(FIXTURE_REQUEST, topic="j2 return mapping")
        assert request_hash(normalize_request(upper)) != request_hash(
            normalize_request(lower)
        )

    @pytest.mark.unit
    def test_normalize_accepts_learning_request_instance(self):
        """normalize_request also accepts a validated LearningRequest object."""
        req = LearningRequest(**FIXTURE_REQUEST)
        assert request_hash(normalize_request(req)) == PINNED_HASH

    @pytest.mark.unit
    def test_to_canonical_dict_matches_normalize(self):
        """to_canonical_dict is an alias of normalize_request."""
        assert to_canonical_dict(FIXTURE_REQUEST) == normalize_request(FIXTURE_REQUEST)
