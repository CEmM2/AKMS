# Documentation Standards

Clear documentation is essential for maintainable simulation code. We want "sufficiently detailed comments without bloat."

## 1. Docstrings (The "What" and "How")

Every public class, function, and `@ti.kernel` must have a docstring.

### Format (Google Style or NumPy Style)
We prefer Google style for consistency.

```python
@ti.kernel
def compute_stress(dt: float):
    """
    Updates particle stress using the Neo-Hookean model.

    Args:
        dt (float): Time step size.

    Notes:
        - Assumes corotational frame.
        - Updates `F` (deformation gradient) and `sigma` (stress).
    """
```

### Essential Information
*   **Purpose**: One sentence summary.
*   **Args**: Type and meaning of each argument.
*   **Returns**: Type and meaning of return value.
*   **Invariants/Assumptions**: e.g., "Input array must be sorted", "dt must be > 0".
*   **Tuning**: Mention any `block_dim` tuning or memory constraints.

## 2. Inline Comments (The "Why")

*   **Do not explain the language**:
    *   *Bad*: `i += 1  # Increment i`
    *   *Good*: `i += 1  # Skip the ghost node`
*   **Explain the math**: Reference equations or papers.
    ```python
    # Update stress using Neo-Hookean energy density:
    # Psi = mu/2 * (Ic - 3) - mu * log(J) + lam/2 * log(J)^2
    ```
*   **Explain Magic Numbers**:
    ```python
    block_dim = 128  # Tuned for RTX 3090, maximizes occupancy
    ```

## 3. READMEs

Each domain folder (e.g., `fem/`, `mpm/`) should have a README explaining:
*   Physical model (equations).
*   Discretization method.
*   How to run examples.

## 4. Avoiding Bloat

*   **No commented-out code**: Delete it. Use git history if you need it back.
*   **No redundant comments**: If the code is `x = mass * acc`, you don't need `# calculate force`.
*   **Keep it fresh**: Wrong documentation is worse than no documentation. Update docs when changing code.
