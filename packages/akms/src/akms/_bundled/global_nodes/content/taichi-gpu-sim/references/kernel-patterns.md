# Kernel Patterns (Taichi GPU) — FEM / FD / Spectral-ish / MPM

This file encodes “house style” for writing Taichi kernels that are fast on GPU: how to structure passes, choose loop forms, manage buffering, and avoid common performance traps.

---

## 1) Kernel anatomy that scales

### Pattern: one responsibility per kernel (mostly)
A good kernel does one of these things:
- **map**: read A, write B (FD updates, G2P, grid update)
- **reduce**: compute a scalar / small vector result (residual norms)
- **scatter**: accumulate into a grid or global vector (P2G, FEM assembly)

Mixing too many responsibilities usually creates:
- branch divergence (boundary logic + interior logic together)
- register pressure (too much live state)
- debugging misery (you will hate future you)

### Pattern: “interior fast path” + “boundary kernel”
For FD/stencils and grid ops:
- Kernel A: update interior indices only (no branches)
- Kernel B: handle boundaries/BCs (branchy, but small)

This avoids warp divergence across the main domain.

---

## 2) Loop forms and compile-time unrolling (use with restraint)

### Pattern: `ti.static` for tiny fixed loops
Use `ti.static` to unroll fixed-size loops:
- stencil taps (e.g., 3×3×3)
- shape function loops (e.g., 3 nodes per axis in quadratic B-spline MPM)
- small matrix ops / Voigt mapping

Taichi explicitly supports compile-time evaluation via `ti.static` (static scope), which helps optimization and reduces runtime overhead.

**Gotcha:** Don’t `ti.static` unroll huge ranges unless you enjoy compile times exploding. Taichi devs have called out misuse of `ti.static` loop unrolling on large loops as a compile-time cost trap.

### Pattern: `ti.ndrange` for multi-D regular loops
Use `ti.ndrange` for structured iteration over ranges; combine with `ti.grouped` when it improves clarity (single index vector). Taichi’s `ti.grouped(ti.ndrange(...))` exists specifically for this “multi-index but one loop variable” pattern.

---

## 3) GPU launch tuning: set block size on hotspot loops

### Pattern: tune `block_dim` on the loop that matters
Use:
- `ti.loop_config(block_dim=128)` (or 256) before the hot loop

Taichi’s performance docs show `ti.loop_config(block_dim=...)` as the intended way to control GPU block size for the *next* loop, and note that a proper choice can yield large speedups.

**Rule:** only tune after profiling. Different kernels want different `block_dim`.

---

## 4) Buffers and time stepping (FD / spectral update loops)

### Pattern: double-buffer (ping-pong) fields
For PDE updates:
- `u_old`, `u_new`
- compute into `u_new`
- swap references after each step (host-side)

Avoid in-place updates unless the scheme is explicitly in-place (most aren’t).

### Pattern: fuse compute + store, but don’t create a “megakernel”
Fusion helps when it removes an intermediate field that was written then immediately re-read (global memory traffic). But if fusion increases branching or register pressure, it can lose.

---

## 5) Reductions and norms (CG/PCG, diagnostics)

### Pattern: reduce into scalar fields (0D) when possible
Use a 0D `ti.field` for reductions (sum of squares, max norm), reset it, reduce, then read on host.
This keeps reductions explicit and avoids creating giant temporary arrays.

**Gotcha:** host reads force sync. Only read diagnostics occasionally.

---

## 6) FEM patterns: matrix-free first, assembly only if you must

### Pattern: matrix-free operator application (Ax)
If you’re doing iterative solvers (CG/PCG), prefer implementing `y = A(x)` without assembling `A`.
Typical structure:
- loop over elements
- compute element-local action in registers (small `ti.Matrix`)
- scatter-add to `y` (atomics often required)

### Pattern: tiny matrices stay tiny
Taichi’s own tutorial guidance: `ti.Matrix` / `ti.Vector` are meant for *small* matrices (think 3×3), not 64×64. For big matrices, use scalar fields/tensors instead.

### Pattern: precompute quadrature + shape grads as compile-time tables
When order and topology are fixed, store weights/shape gradients in Python lists/tuples and iterate via `ti.static` so the compiler bakes them in (fast, deterministic).

**Gotcha:** assembly scatter is atomic-heavy. If profiling shows atomics dominate, you need an algorithmic change (coloring, two-pass staging, matrix-free, etc.), not micro-tweaks.

---

## 7) MPM patterns: canonical 3-pass, with optional fusion

### Baseline pass structure (classic)
1. **Clear grid**
2. **P2G**: particle → grid scatter (mass/momentum/affine terms)
3. **Grid ops**: forces, gravity, BCs, normalization
4. **G2P**: grid → particle gather (update v/x/F/etc.)

This P2G/G2P structure is the standard MPM “particle-grid interaction” breakdown.

### Pattern: quadratic B-spline weights with `ti.static` 3×3×3
The common Taichi MPM snippet uses:
- `base = int(Xp - 0.5)`
- `w[0..2] = ...` (quadratic weights)
- `for i,j,k in ti.static(range(3))` for the 27 neighbor nodes

This exact structure shows up across Taichi MPM examples/issues and is widely reused.

### Pattern: fuse G2P2G when it’s worth it (advanced)
Some implementations support an optimized fused path (often called “G2P2G fused”), which can reduce passes and memory traffic, but it complicates correctness and debugging.

**Rule:** start with the 3-pass approach, profile, then consider fusion.

### Atomics reality check
P2G scatter is an atomic contention hotspot. You mitigate with:
- layout choices (grid tiling/blocking)
- reducing writes (accumulate locally then atomic once per node/component)
- algorithmic variants (domain decomposition, coloring, staging)

---

## 8) Spectral-ish patterns: keep Taichi for glue, interop for serious FFT

### Pattern: Taichi for pointwise ops + PDE glue
Use Taichi for:
- pointwise multiplications in spectral space
- dealiasing masks
- nonlinear term assembly
- RK stages / time stepping structure

But if you need a production-grade FFT, plan interop with vendor FFT libraries. (Taichi is great, but it’s not a full FFT library by default.)

---

## 9) Debug-friendly kernel style (without destroying performance)

### Pattern: debug mode toggles
- Keep a `debug` flag that enables extra checks in separate kernels or infrequent steps.
- Avoid printing in hot kernels.

### Pattern: invariants as cheap tests
Examples:
- mass conservation (MPM)
- symmetry checks (FEM operators)
- residual monotonic decrease (CG)
- NaN/Inf scans occasionally

---

## 10) Micro-templates (structure, not full code)

These are *structure templates*, not full implementations. They exist so you don’t reinvent a slow kernel layout every time.

### FD stencil update (interior-only, branch-free)
Use grouped **ndrange** when you want custom bounds (e.g., interior only) so you avoid boundary branching.

- `ti.loop_config(block_dim=...)` immediately before the hotspot loop
- `for I in ti.grouped(ti.ndrange((1, nx-1), (1, ny-1), ...))`
- load neighbors (regular offsets)
- compute update
- write `u_new[I]`

Example structure:

```python
@ti.kernel
def fd_step(u_old: ti.template(), u_new: ti.template(), nx: int, ny: int, nz: int):
    # Interior update only: [1, n-2] to avoid boundary branches
    ti.loop_config(block_dim=256)
    for I in ti.grouped(ti.ndrange((1, nx - 1), (1, ny - 1), (1, nz - 1))):
        # load neighbors from u_old[I + offset]
        # compute update
        u_new[I] = 0.0  # placeholder
```

- Boundary conditions should be handled in a separate kernel.

**Nuance**: for full-domain sweeps (copy/scale/pointwise ops), prefer grouped struct-for:
- `for I in ti.grouped(u)`
  This iterates the field’s index space (and respects sparse activation when applicable).

### FEM matrix-free Ax (operator application)
- zero `y`
- loop elements (and quadrature points if used)
- compute element-local action in small `ti.Matrix/ti.Vector` (register-resident)
- scatter-add into `y` (atomics unless you use coloring/staging)

Structure sketch:
```python
@ti.kernel
def apply_A(x: ti.template(), y: ti.template()):
    # y = 0
    for I in y:
        y[I] = 0.0

    # element loop
    for e in range(n_elem):
        # compute local contributions (register math)
        # scatter-add to y (atomic adds)
        pass
```

### MPM step (canonical passes)
- clear grid
- P2G scatter (weights, atomics)
- grid normalize + forces + BCs
- G2P gather + particle update
- (optional) fused variant when validated + profiled

Structure sketch:

```python
@ti.kernel
def clear_grid():
    for I in grid_m:
        grid_m[I] = 0.0
        grid_v[I] = ti.Vector.zero(ti.f32, 3)

@ti.kernel
def p2g():
    # particles → grid (scatter, atomics)
    pass

@ti.kernel
def grid_op():
    # normalize, forces, BCs
    pass

@ti.kernel
def g2p():
    # grid → particles (gather)
    pass
```

---

## 11) Gotchas that keep showing up
- Unrolling huge loops with `ti.static` can blow up compile time.
- Kernel launch tuning (`block_dim`) only applies to the *next* loop; put it right before the hotspot loop.
- `ti.Matrix` is for small matrices; do not build giant matrices out of it.