# Interface Compatibility & Breaking Changes

One of the reviewer's key roles is to protect existing consumers from breaking changes.

## 1. Defining "Breaking Change"

A breaking change is any modification that causes code relying on the previous version to fail or behave differently (incorrectly).

### Examples:
*   **Renaming** a public function or class.
*   **Removing** a public function or class.
*   **Adding a required argument** to a function.
*   **Changing the return type** of a function.
*   **Changing the shape/layout** of a public field (SNode).
*   **Changing physical unit conventions** (e.g., from Pa to MPa).
*   **Changing sign conventions** (e.g., tension-positive to compression-positive).

## 2. Review Strategy

When reviewing a PR, look for these patterns:

### Function Signatures
*   *Safe*: Adding an optional argument (`def func(..., new_arg=None):`).
*   *Unsafe*: Adding a required argument (`def func(..., new_arg):`).
*   *Unsafe*: Reordering arguments.

### Data Structures
*   *Safe*: Appending a new field to a class (if it doesn't disrupt memory layout logic elsewhere).
*   *Unsafe*: Changing the definition of a Taichi field (e.g., `ti.root.dense(ti.i, N)` -> `ti.root.dense(ti.ij, (N, N))`).

### Behavior
*   *Unsafe*: Changing the default value of a parameter.
*   *Unsafe*: Fixing a "bug" that users might depend on (Hyrum's Law).

## 3. How to Handle Breaking Changes

If a breaking change is necessary:

1.  **Deprecation Warning**: Mark the old interface as deprecated but keep it working if possible.
    ```python
    import warnings
    def old_func():
        warnings.warn("Use new_func instead", DeprecationWarning)
        return new_func()
    ```
2.  **Version Bump**: Signal the change via semantic versioning (Major version bump).
3.  **Migration Guide**: Document how users should update their code.

## 4. Taichi Specifics

*   **Kernel Compilation**: Changing a `@ti.kernel` signature forces recompilation. This is usually fine but can affect performance.
*   **Serialized Data**: If the simulation saves checkpoints (e.g., `ti.ndarray.to_numpy().save()`), changing the data layout will break loading of old checkpoints.
