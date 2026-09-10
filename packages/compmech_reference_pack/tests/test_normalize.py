"""normalize_algpseudocode — the LSP→algo2code normalisation pass.

Acceptance:
  - a radial-return node normalises to algo2code-clean text that transpiles;
  - parser errors come back as structured warnings, never a crash.
"""

from __future__ import annotations

import pytest
from compmech_reference_pack.normalize import (
    NormalizationResult,
    extract_algorithmic_block,
    normalize,
    normalize_algpseudocode,
)

# Human-authored excerpt: markdown prose + a fenced algorithmic block, no
# % directives (the common LSP-node shape).
_RADIAL_RETURN_MD = r"""
## Radial-return update

Given the trial von Mises stress, solve for the plastic multiplier increment.

```latex
\begin{algorithmic}
\State $sy \gets sigy0 + K \cdot \alpha^{n}$
\State $f = sigma_eq - sy$
\If{$f < 0$}
\State $dl = 0$
\Else
\State $dl = f / (3 \cdot mu)$
\EndIf
\end{algorithmic}
```
"""


@pytest.mark.unit
def test_extract_block_strips_fences_and_markers() -> None:
    body = extract_algorithmic_block(_RADIAL_RETURN_MD)
    assert body is not None
    assert r"\begin{algorithmic}" not in body
    assert "sigma_eq" in body


@pytest.mark.unit
def test_synthesises_algorithm_name_and_backend() -> None:
    out = normalize_algpseudocode(_RADIAL_RETURN_MD, algorithm_name="radial_return_j2")
    assert "% algorithm radial_return_j2" in out
    assert "% backend taichi" in out


@pytest.mark.unit
def test_normalised_radial_return_transpiles() -> None:
    """The headline AC: a radial-return node transpiles after normalisation."""
    from mechdsl.integration import transpile_algorithm

    out = normalize_algpseudocode(_RADIAL_RETURN_MD, algorithm_name="radial_return_j2")
    result = transpile_algorithm(out, backend="taichi")
    assert result["valid_python"], result["code"]
    assert result["entry_point"] == "radial_return_j2"


@pytest.mark.unit
def test_no_block_warns_not_crashes() -> None:
    result = normalize("Just prose. No algorithm here.")
    assert isinstance(result, NormalizationResult)
    assert result.algorithmic_block_found is False
    assert result.warnings
    # Still returns a (trivial) normalised source rather than crashing.
    assert r"\begin{algorithmic}" in result.normalized


@pytest.mark.unit
def test_malformed_math_surfaced_as_warning_not_crash() -> None:
    bad = "\n".join(
        [r"\begin{algorithmic}", r"\State $y = @@@ $", r"\end{algorithmic}"]
    )
    # Must not raise, regardless of whether algo2code accepts the input.
    result = normalize(bad)
    assert result.algorithmic_block_found is True
    if not result.parses:
        assert any("parse failed" in w for w in result.warnings)


@pytest.mark.unit
def test_author_directives_preserved() -> None:
    src = "\n".join(
        [
            "% algorithm my_solver",
            "% args x:scalar",
            r"\begin{algorithmic}",
            r"\State $y = x \cdot x$",
            r"\end{algorithmic}",
        ]
    )
    out = normalize_algpseudocode(src)
    assert "% algorithm my_solver" in out
    assert "% args x:scalar" in out
    # No duplicate synthesised name.
    assert out.count("% algorithm ") == 1


@pytest.mark.unit
def test_bare_algorithm_directive_not_duplicated() -> None:
    """A name-less '% algorithm' author directive must not get a synthesised twin."""
    src = "\n".join(
        [
            "% algorithm",
            r"\begin{algorithmic}",
            r"\State $y = x \cdot x$",
            r"\end{algorithmic}",
        ]
    )
    out = normalize_algpseudocode(src)
    # Exactly one algorithm directive (the author's bare one), no synthesised dup.
    assert (
        sum(1 for line in out.splitlines() if line.strip().startswith("% algorithm"))
        == 1
    )
