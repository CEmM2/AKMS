"""Shared fixtures for the akms-learn test suite."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from akms_learn import LearningRequest


@pytest.fixture
def make_request() -> Callable[..., LearningRequest]:
    """Build a minimal :class:`LearningRequest` for the fixture graph.

    Keyword overrides replace any default, so cases that need a non-default
    ``exporters`` list, topic, or generation option can pass them inline:

        req = make_request(exporters=["markdown"])
    """

    def _build(**overrides) -> LearningRequest:
        defaults = dict(
            topic="j² return mapping",
            goal="Understand the j² return-mapping algorithm",
            audience="engineer",
            depth="implementation",
            generation_option="deterministic_outline",
            seed_tags=[],
            exporters=["markdown", "bundle"],
        )
        defaults.update(overrides)
        return LearningRequest(**defaults)

    return _build
