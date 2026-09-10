---
name: gen-test
description: Generate tests for a Taichi FEM module following the tiered testing conventions (Tier A/B/C) with proper tolerances and GPU backend handling.
user-invocable: true
arguments:
  - name: module
    description: The module path or file to generate tests for (e.g., myfem.elements.tl_hex8)
    required: true
  - name: tier
    description: "Test tier: A (fast unit), B (kernel/GPU), C (integration/E2E)"
    default: "A"
---

# Generate Taichi FEM Tests

## Prime directive
Generate correct, focused tests that follow the project's tiered testing conventions and numerical safeguards.

## Workflow

### 1. Identify the module under test
- Read the target module to understand its API, inputs, outputs, and edge cases.
- Check for existing tests in `tests/` that cover the same module — avoid duplication.

### 2. Determine the test tier

| Tier | Scope | Speed | Examples |
|------|-------|-------|----------|
| **A** | Pure math, shapes, serialization, utils | < 1s each | Shape function values, tensor ops, YAML round-trips |
| **B** | Taichi kernel correctness | < 10s each | Element stiffness, constitutive updates, assembly kernels |
| **C** | Full simulation pipelines | < 60s each | Quasi-static solve, phase-field fracture, coupled problems |

### 3. Apply tier-specific conventions

#### Tier A — Unit tests
```python
import pytest
import numpy as np

class TestModuleName:
    """Unit tests for [module]."""

    def test_basic_output(self):
        # Direct function call, assert exact or near-exact values
        result = module_function(input)
        np.testing.assert_allclose(result, expected, rtol=1e-12)
```

#### Tier B — Kernel tests
```python
import pytest
import taichi as ti
import numpy as np

@pytest.fixture(autouse=True)
def ti_scope():
    ti.init(arch=ti.cpu, default_fp=ti.f64)
    yield
    ti.reset()

class TestKernelName:
    """Kernel correctness tests for [module]."""

    def test_kernel_output_f64(self):
        # Initialize fields, run kernel, compare to reference
        result = field.to_numpy()
        np.testing.assert_allclose(result, reference, rtol=1e-10)

    def test_kernel_output_f32(self):
        # Same test with f32 precision
        np.testing.assert_allclose(result, reference, rtol=1e-5)
```

#### Tier C — Integration tests
```python
import pytest

@pytest.mark.slow
class TestSimulation:
    """E2E integration test for [simulation type]."""

    def test_full_solve_converges(self):
        # Set up minimal mesh, BCs, material
        # Run simulation
        # Assert convergence, no NaN/Inf, physical plausibility
        assert not np.any(np.isnan(result))
        assert not np.any(np.isinf(result))
```

### 4. Numerical safeguards (always include)
- **NaN/Inf checks**: Assert outputs are finite.
- **Tolerance selection**: `rtol=1e-10` for f64, `rtol=1e-5` for f32.
- **GPU nondeterminism**: For Tier B tests with atomics, use `atol=1e-6` to account for floating-point ordering.
- **Reference values**: Prefer analytically known solutions. If not available, use a validated reference implementation and document the source.

### 5. File placement
- Place test files in `tests/` with naming: `test_<module_name>.py`
- For thirdparty module tests, check `thirdparty/tisolvers/tests/` and `thirdparty/ticonstit/tests/` first.

### 6. Run and verify
```bash
uv run pytest tests/test_<module_name>.py -v
```
