"""required-unavailable capability hard failure.

Per the specification rule 5 / spec §4 rule 2: a learning request that lists a
capability in ``required_capabilities`` which the plugin does NOT provide
MUST raise :class:`LearningCapabilityError`. The CLI surfaces this as exit
code 3 (see ``cli.main``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_learn import cli
from akms_learn.compiler import compile_learning_source
from akms_learn.domain_packs import LearningCapabilityError
from akms_learn.graph_import import fixture_graph

# A capability string that is intentionally absent from
# ``akms_learn.plugin.Plugin.capabilities()``. The plugin currently ships
# 10 capabilities (6 §7 originals + 4 §21 domain-pack additions); this
# made-up name is guaranteed to be missing.
_UNAVAILABLE_CAPABILITY = "executable_companion_runner"


def _base_request() -> dict[str, object]:
    return {
        "topic": "j2_return_mapping",
        "goal": "Trigger a hard capability failure.",
        "audience": "engineer",
        "depth": "implementation",
        "generation_option": "deterministic_outline",
        "required_capabilities": [_UNAVAILABLE_CAPABILITY],
    }


@pytest.mark.integration
def test_required_unavailable_capability_error(tmp_path: Path) -> None:
    """compile_learning_source raises LearningCapabilityError on
    required-but-unavailable capabilities."""
    with pytest.raises(LearningCapabilityError) as exc_info:
        compile_learning_source(
            request=_base_request(),
            graph_slice=fixture_graph(),
            output_dir=tmp_path,
        )
    assert _UNAVAILABLE_CAPABILITY in str(exc_info.value)


@pytest.mark.integration
def test_cli_required_unavailable_exit_code_3(tmp_path: Path) -> None:
    """Invoking the CLI with an unavailable required capability returns 3.

    The CLI itself does not have a ``--required-capability`` flag (per the
    by design); we trigger the same failure path by patching
    ``cli.compile_learning_source`` with a stub that raises
    :class:`LearningCapabilityError`. This validates the CLI's exception
    translation contract (exit code 3) without coupling to a future flag.
    """

    def _raise(**_kwargs: object) -> None:
        raise LearningCapabilityError(
            f"Required capability/capabilities unavailable: "
            f"[{_UNAVAILABLE_CAPABILITY!r}]"
        )

    # Use monkeypatch via direct attribute substitution + try/finally so the
    # test is monkeypatch-fixture-free (works the same in both runners).
    original = cli.compile_learning_source
    cli.compile_learning_source = _raise  # type: ignore[assignment]
    try:
        exit_code = cli.main(
            [
                "compile",
                "--graph",
                "fixture",
                "--topic",
                "j2_return_mapping",
                "--output",
                str(tmp_path),
            ]
        )
    finally:
        cli.compile_learning_source = original  # type: ignore[assignment]

    assert exit_code == 3, (
        f"CLI must exit with code 3 on LearningCapabilityError; got {exit_code}"
    )
