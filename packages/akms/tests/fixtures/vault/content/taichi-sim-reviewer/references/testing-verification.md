# Testing & Verification Strategy

We follow the **Tiered Testing Strategy** defined in `taichi-gpu-sim`.

## 1. Verify Test Coverage for New Code

When reviewing new code, ask: "Where does this fit in the testing tiers?"

*   **Tier A (Pure Math)**: New math utility (e.g., a new tensor operation)?
    *   *Requirement*: Must have a unit test running in standard Python (NumPy/SymPy) checking correctness. Fast execution (<1s).
*   **Tier B (Kernels)**: New Taichi kernel?
    *   *Requirement*: Unit test calling the kernel with small, deterministic inputs. Verify against reference implementation.
*   **Tier C (Integration)**: New physics feature (e.g., plasticity model)?
    *   *Requirement*: Patch test (single element/particle) ensuring stress states are correct.
*   **Tier D (Performance)**: Optimization?
    *   *Requirement*: Benchmark comparing old vs. new runtime.

## 2. Regression Testing

Ensure that modifications do not break existing functionality.

*   **Run All Tests**: `pytest tests/` (or equivalent command).
*   **Check Invariants**:
    *   Conservation of mass/energy.
    *   Symmetry of stress tensors.
    *   Objectivity (rigid body rotation).
*   **Fixing Regressions**:
    *   If a test fails, do not just update the test to match new behavior unless the old behavior was provably wrong.
    *   Investigate if the failure indicates a breaking change or a bug.

## 3. Adding New Tests

When adding a new test, follow these rules:

1.  **Determinism**: Use fixed seeds for random number generators.
2.  **Size**: Keep unit tests small (e.g., 4x4 grid, 10 particles). Large simulations belong in benchmarks, not CI.
3.  **Tolerances**:
    *   `f32`: `rtol=1e-5`, `atol=1e-6`
    *   `f64`: `rtol=1e-10`, `atol=1e-12`
4.  **No Flakiness**: Tests must pass 100% of the time. Avoid race conditions in tests.

## 4. SymPy Verification

For complex mathematical derivations (e.g., tangent stiffness matrices, stress updates), encourage the use of SymPy scripts to verify the implementation.

*   See `taichi-gpu-sim/references/testing-and-validation.md` for examples of SymPy verification scripts.
