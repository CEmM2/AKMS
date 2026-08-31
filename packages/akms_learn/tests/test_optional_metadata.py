"""Tests for the optional AKMS v2.1 metadata support layer.

AC covered:
- V21Metadata exposes all six optional fields with safe defaults.
- read_v21_metadata returns a defaulted instance on absent v2.1 fields.
- expansion_policy accepts exactly {source_locked, explanatory_only, no_new_claims}.
- Nodes without v2.1 fields continue to compile (no regression — see test_compile_integration.py).
- read_v21_metadata never writes to the node or vault (canary test).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from akms_learn.optional_metadata import (
    EXPANSION_POLICY_VALUES,
    V21Metadata,
    V21MetadataError,
    read_v21_metadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bare_node(**extra: Any) -> dict[str, Any]:
    """Return a minimal node dict that may contain extra v2.1 fields."""
    base: dict[str, Any] = {
        "node_id": "test-node-001",
        "title": "Test Node",
        "domain": "testing",
        "tags": ["test"],
        "status": "established",
        "confidence": 0.9,
        "source": "human",
        "akms_schema": "v2",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# V21Metadata exposes all six optional fields with safe defaults
# ---------------------------------------------------------------------------


class TestV21MetadataDefaults:
    """Model has all six optional fields with safe defaults."""

    @pytest.mark.unit
    def test_all_six_fields_present(self) -> None:
        """All six v2.1 fields exist on the model."""
        meta = V21Metadata()
        assert hasattr(meta, "expansion_policy")
        assert hasattr(meta, "llm_allowed")
        assert hasattr(meta, "generated_section_validation")
        assert hasattr(meta, "learner_profile")
        assert hasattr(meta, "skipped_prerequisites")
        assert hasattr(meta, "assessment_items")

    @pytest.mark.unit
    def test_default_expansion_policy_is_none(self) -> None:
        assert V21Metadata().expansion_policy is None

    @pytest.mark.unit
    def test_default_llm_allowed_is_none(self) -> None:
        assert V21Metadata().llm_allowed is None

    @pytest.mark.unit
    def test_default_generated_section_validation_is_none(self) -> None:
        assert V21Metadata().generated_section_validation is None

    @pytest.mark.unit
    def test_default_learner_profile_is_none(self) -> None:
        assert V21Metadata().learner_profile is None

    @pytest.mark.unit
    def test_default_skipped_prerequisites_is_empty_tuple(self) -> None:
        assert V21Metadata().skipped_prerequisites == ()

    @pytest.mark.unit
    def test_default_assessment_items_is_empty_tuple(self) -> None:
        assert V21Metadata().assessment_items == ()

    @pytest.mark.unit
    def test_model_is_frozen(self) -> None:
        """V21Metadata must be immutable (frozen=True)."""
        meta = V21Metadata()
        with pytest.raises(Exception):  # pydantic raises ValidationError or TypeError
            meta.llm_allowed = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# read_v21_metadata returns defaulted instance on absent fields
# ---------------------------------------------------------------------------


class TestAbsentFields:
    """Absent v2.1 fields → fully-defaulted V21Metadata, no exception."""

    @pytest.mark.unit
    def test_bare_node_returns_v21metadata_instance(self) -> None:
        node = _bare_node()
        meta = read_v21_metadata(node)
        assert isinstance(meta, V21Metadata)

    @pytest.mark.unit
    def test_bare_node_all_defaults(self) -> None:
        node = _bare_node()
        meta = read_v21_metadata(node)
        assert meta == V21Metadata()

    @pytest.mark.unit
    def test_empty_dict_returns_defaults(self) -> None:
        """Even an empty dict works — all fields absent → all defaults."""
        meta = read_v21_metadata({})
        assert meta == V21Metadata()

    @pytest.mark.unit
    def test_no_exception_on_absent_fields(self) -> None:
        """read_v21_metadata must never raise on a node with no v2.1 fields."""
        try:
            read_v21_metadata(_bare_node())
        except Exception as exc:
            pytest.fail(f"Unexpected exception on absent fields: {exc!r}")


# ---------------------------------------------------------------------------
# (partial fields): only set fields populated, others remain default
# ---------------------------------------------------------------------------


class TestPartialFields:
    """Partial v2.1 fields → set fields populated, absent fields at defaults."""

    @pytest.mark.unit
    def test_only_expansion_policy_set(self) -> None:
        node = _bare_node(expansion_policy="source_locked")
        meta = read_v21_metadata(node)
        assert meta.expansion_policy == "source_locked"
        assert meta.llm_allowed is None
        assert meta.generated_section_validation is None
        assert meta.learner_profile is None
        assert meta.skipped_prerequisites == ()
        assert meta.assessment_items == ()

    @pytest.mark.unit
    def test_only_llm_allowed_set(self) -> None:
        node = _bare_node(llm_allowed=False)
        meta = read_v21_metadata(node)
        assert meta.llm_allowed is False
        assert meta.expansion_policy is None

    @pytest.mark.unit
    def test_only_learner_profile_set(self) -> None:
        node = _bare_node(learner_profile="beginner")
        meta = read_v21_metadata(node)
        assert meta.learner_profile == "beginner"
        assert meta.expansion_policy is None

    @pytest.mark.unit
    def test_skipped_prerequisites_sorted_deterministically(self) -> None:
        """skipped_prerequisites must be sorted for cross-phase determinism."""
        node = _bare_node(skipped_prerequisites=["z-node", "a-node", "m-node"])
        meta = read_v21_metadata(node)
        assert meta.skipped_prerequisites == ("a-node", "m-node", "z-node")

    @pytest.mark.unit
    def test_assessment_items_preserved_as_tuple(self) -> None:
        items = [
            {"type": "mcq", "question": "What is X?"},
            {"type": "fib", "prompt": "Fill in"},
        ]
        node = _bare_node(assessment_items=items)
        meta = read_v21_metadata(node)
        assert isinstance(meta.assessment_items, tuple)
        assert len(meta.assessment_items) == 2
        assert meta.assessment_items[0]["type"] == "mcq"

    @pytest.mark.unit
    def test_all_six_fields_set(self) -> None:
        """All six fields populated simultaneously."""
        node = _bare_node(
            expansion_policy="explanatory_only",
            llm_allowed=True,
            generated_section_validation="strict",
            learner_profile="intermediate",
            skipped_prerequisites=["prereq-b", "prereq-a"],
            assessment_items=[{"type": "mcq", "q": "Q1"}],
        )
        meta = read_v21_metadata(node)
        assert meta.expansion_policy == "explanatory_only"
        assert meta.llm_allowed is True
        assert meta.generated_section_validation == "strict"
        assert meta.learner_profile == "intermediate"
        assert meta.skipped_prerequisites == ("prereq-a", "prereq-b")  # sorted
        assert meta.assessment_items == ({"type": "mcq", "q": "Q1"},)


# ---------------------------------------------------------------------------
# expansion_policy validates exactly {source_locked, explanatory_only, no_new_claims}
# ---------------------------------------------------------------------------


class TestExpansionPolicy:
    """Expansion_policy validation."""

    @pytest.mark.unit
    @pytest.mark.parametrize("policy", sorted(EXPANSION_POLICY_VALUES))
    def test_valid_expansion_policy_accepted(self, policy: str) -> None:
        node = _bare_node(expansion_policy=policy)
        meta = read_v21_metadata(node)
        assert meta.expansion_policy == policy

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "bad_policy",
        [
            "unrestricted",
            "locked",
            "source locked",  # space instead of underscore
            "SOURCE_LOCKED",  # wrong case
            "",
            "none",
            "no_new_claim",  # typo
            "explanatory_Only",
        ],
    )
    def test_invalid_expansion_policy_raises(self, bad_policy: str) -> None:
        node = _bare_node(expansion_policy=bad_policy)
        with pytest.raises(V21MetadataError):
            read_v21_metadata(node)

    @pytest.mark.unit
    def test_expansion_policy_error_mentions_allowed_values(self) -> None:
        """Error message must mention the allowed value set."""
        node = _bare_node(expansion_policy="bad_value")
        with pytest.raises(V21MetadataError, match="source_locked"):
            read_v21_metadata(node)

    @pytest.mark.unit
    def test_none_expansion_policy_is_valid(self) -> None:
        """None (absent) is always valid — means no policy set."""
        node = _bare_node()
        meta = read_v21_metadata(node)
        assert meta.expansion_policy is None


# ---------------------------------------------------------------------------
# read_v21_metadata never writes to node or vault (canary)
# ---------------------------------------------------------------------------


class TestVaultCanary:
    """No filesystem writes occur during metadata reads."""

    @pytest.mark.unit
    def test_node_dict_not_mutated(self) -> None:
        """The input dict must be byte-identical before and after the call."""
        import copy

        node = _bare_node(
            expansion_policy="no_new_claims",
            skipped_prerequisites=["p1"],
        )
        node_before = copy.deepcopy(node)
        read_v21_metadata(node)
        assert node == node_before

    @pytest.mark.unit
    def test_no_write_to_global_vault_default_path(self) -> None:
        """Canary: Path.write_text / open(w) must not touch ~/.claude/akms/nodes/."""
        vault_path = Path("~/.claude/akms/nodes").expanduser()

        calls: list[Path] = []

        original_write_text = Path.write_text

        def spy_write_text(self: Path, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
            calls.append(self)
            return original_write_text(self, *args, **kwargs)

        with patch.object(Path, "write_text", spy_write_text):
            read_v21_metadata(_bare_node(llm_allowed=True))

        vault_calls = [p for p in calls if str(p).startswith(str(vault_path))]
        assert vault_calls == [], (
            f"read_v21_metadata wrote to vault path(s): {vault_calls}"
        )

    @pytest.mark.unit
    def test_no_makedirs_under_vault(self) -> None:
        """Canary: os.makedirs must not be called for any vault sub-path."""
        vault_str = str(Path("~/.claude/akms/nodes").expanduser())

        with patch("os.makedirs") as mock_makedirs:
            read_v21_metadata(_bare_node())
        for call in mock_makedirs.call_args_list:
            path_arg = str(call.args[0]) if call.args else ""
            assert not path_arg.startswith(vault_str), (
                f"os.makedirs called under vault: {path_arg}"
            )

    @pytest.mark.unit
    def test_no_write_to_akms_global_vault_env_override(self, tmp_path: Path) -> None:
        """Canary: vault writes blocked even when AKMS_GLOBAL_VAULT is overridden."""
        fake_vault = tmp_path / "fake_vault"
        fake_vault.mkdir()

        calls: list[Path] = []
        original_write_text = Path.write_text

        def spy_write_text(self: Path, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
            calls.append(self)
            return original_write_text(self, *args, **kwargs)

        with (
            patch.dict(os.environ, {"AKMS_GLOBAL_VAULT": str(fake_vault)}),
            patch.object(Path, "write_text", spy_write_text),
        ):
            read_v21_metadata(_bare_node())

        vault_calls = [p for p in calls if str(p).startswith(str(fake_vault))]
        assert vault_calls == [], (
            f"read_v21_metadata wrote under AKMS_GLOBAL_VAULT: {vault_calls}"
        )


# ---------------------------------------------------------------------------
# Determinism: sorted collection access
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Cross-phase determinism contract: sorted collection access."""

    @pytest.mark.unit
    def test_skipped_prerequisites_stable_across_calls(self) -> None:
        node = _bare_node(skipped_prerequisites=["c", "a", "b"])
        first = read_v21_metadata(node)
        second = read_v21_metadata(node)
        assert (
            first.skipped_prerequisites
            == second.skipped_prerequisites
            == ("a", "b", "c")
        )

    @pytest.mark.unit
    def test_assessment_items_order_preserved(self) -> None:
        """assessment_items preserve insertion order (not sorted — they are ordered hints)."""
        items = [{"id": 3}, {"id": 1}, {"id": 2}]
        node = _bare_node(assessment_items=items)
        meta = read_v21_metadata(node)
        assert [d["id"] for d in meta.assessment_items] == [3, 1, 2]
