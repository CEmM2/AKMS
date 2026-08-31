"""Schema tests: ModelRoutingConfig on PropagationConfig.

Covers:
- ModelRoutingEntry defaults (provider='anthropic', model='claude-haiku-4-5-20251001')
- ModelRoutingConfig field structure (dedup_similarity, docstring_drift)
- PropagationConfig.model_routing optional field integration
- Schema backward compatibility (no version bump)
"""

from __future__ import annotations

import pytest

from akms.schema.models import PropagationConfig, ModelRoutingConfig, ModelRoutingEntry


class TestADM003ModelRoutingSchema:
    """
    ModelRoutingConfig on PropagationConfig.
    Acceptance criteria covered: 1-4
    """

    @pytest.mark.unit
    def test_propagation_config_defaults_include_model_routing(self):
        """PropagationConfig() (no args) creates valid config with default model_routing.

        Acceptance criterion 3: PropagationConfig() (no args) creates valid config with default model_routing
        """
        config = PropagationConfig()
        assert isinstance(config.model_routing, ModelRoutingConfig)

    @pytest.mark.unit
    def test_model_routing_entry_default_provider_model(self):
        """ModelRoutingEntry defaults to provider='anthropic', model='claude-haiku-4-5-20251001'.

        Acceptance criterion 1: ModelRoutingEntry defaults to provider='anthropic', model='claude-haiku-4-5-20251001'
        """
        entry = ModelRoutingEntry()
        assert entry.provider == "anthropic"
        assert entry.model == "claude-haiku-4-5-20251001"

    @pytest.mark.unit
    def test_model_routing_config_has_dedup_similarity_docstring_drift(self):
        """ModelRoutingConfig has dedup_similarity and docstring_drift fields.

        Acceptance criterion 2: ModelRoutingConfig has dedup_similarity and docstring_drift fields
        """
        config = ModelRoutingConfig()
        assert isinstance(config.dedup_similarity, ModelRoutingEntry)
        assert isinstance(config.docstring_drift, ModelRoutingEntry)

    @pytest.mark.unit
    def test_propagation_config_model_validate_with_explicit_model_routing(self):
        """PropagationConfig.model_validate({'model_routing': {...}}) works with explicit values.

        Acceptance criterion 4: PropagationConfig.model_validate({'model_routing': {...}}) works with explicit values
        """
        config = PropagationConfig.model_validate(
            {"model_routing": {"dedup_similarity": {"provider": "gemini", "model": "gemini-2.0-flash"}}}
        )
        assert config.model_routing.dedup_similarity.provider == "gemini"
        assert config.model_routing.dedup_similarity.model == "gemini-2.0-flash"

    @pytest.mark.unit
    def test_existing_propagation_config_backward_compat(self):
        """Existing PropagationConfig tests still pass — this is an additive optional field.

        Acceptance criterion 5: Existing schema tests pass unchanged — this is an additive optional field
        """
        # No-args construction works
        config = PropagationConfig()
        assert config is not None

        # Construction with existing fields (no model_routing) works
        config2 = PropagationConfig.model_validate({"global_vault": "~/.claude/akms/nodes"})
        assert config2 is not None
        assert isinstance(config2.model_routing, ModelRoutingConfig)

    @pytest.mark.unit
    def test_schema_version_remains_v2(self):
        """akms_schema remains v2 (no version bump).

        Acceptance criterion 6: akms_schema remains v2 (no version bump)
        """
        config = PropagationConfig()
        assert config.akms_schema == "v2"
