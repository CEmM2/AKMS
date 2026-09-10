---
name: taichi-gpu-sim
description: Writes optimized Taichi (taichi-lang) code for GPU numerical simulation, focusing on performant kernels, data layout/SNode design, and solver patterns for FEM, finite differences (FD), FFT-like spectral methods, and MPM. Use when implementing or optimizing Taichi kernels, choosing fields/SNodes, reducing atomics, tuning block dimensions, or debugging GPU performance/correctness.
---

# Writing Taichi GPU Simulation Code (FEM / FD / FFT / MPM)

## Prime directive
Write Taichi code that is **correct first**, then **fast**, and stays **fast** as problem size grows.

Default assumptions unless the user specifies otherwise:
- GPU backend (`ti.gpu` / CUDA / Vulkan / Metal depending on platform)
- `f64` unless the user requires `f32`
- Performance-critical loops run inside `@ti.kernel` / `@ti.func`
- Prefer data-parallel, predictable memory access

## Workflow (use this every time)
1. **Clarify the target**: backend (CUDA/Vulkan/Metal), dimension (2D/3D), grid/mesh sizes, precision, and where time is spent.
2. **Choose data layout first** (fields/SNodes): aim for coalesced access and minimal memory traffic.
3. **Kernelize the hot path**: minimize Python-side loops, kernel launches, and sync points.
4. **Reduce atomics + divergence**: they are performance poison on GPU.
5. **Tune launch**: use `ti.loop_config(block_dim=...)` for GPU thread-block sizing when it matters. (`ti.block_dim` is deprecated.) 
6. **Validate**: numerical sanity checks (conservation, symmetry, residual decrease), then profile again.

## Performance rules of thumb (GPU)
### Data layout
- Prefer **Structure-of-Arrays** patterns for streaming math (common in FD/MPM).
- Use small fixed-size `ti.Vector/ti.Matrix` for per-particle/per-node state (MPM/FEM).
- Keep frequently accessed fields compact and aligned.

### Kernel structure
- Fuse passes if it reduces global memory traffic (but don’t create unreadable monster kernels).
- Use `ti.static` for compile-time loops over small fixed ranges (shape functions, quadrature points, stencil taps).
- Prefer `ti.ndrange` / `ti.grouped` where it improves indexing clarity and performance.

### Atomics & reductions
- Avoid naive scatter-add everywhere. If you must scatter, consider:
  - reducing atomics via per-thread accumulation strategies
  - algorithmic tricks (coloring, staging, two-pass reductions)
- Be aware Taichi can apply TLS-style reduction optimizations for certain reductions on 0D fields (not `ti.ndarray`). 

### Loop launch tuning
- Use `ti.loop_config(block_dim=...)` to set GPU block size for the *next* loop when beneficial.
- Start with common values (e.g., 128/256) then validate via profiling; tune per kernel.

## Domain playbooks (quick guidance)
### FEM (assembly / matrix-free)
- Prefer **matrix-free operator application** for iterative solvers (CG/PCG) when memory-bound.
- If assembling:
  - element-local compute in registers (`ti.Matrix` small fixed sizes)
  - scatter to global vectors with atomics only where necessary
- Precompute shape grads / quadrature weights in `ti.static` tables for speed and determinism.
- Boundary conditions: apply in a dedicated pass (avoid branching in the main operator if possible).

See: `domains/fem.md`

### FD (stencils / PDE time stepping)
- Use **double-buffering** (`u_old`, `u_new`) and swap references each step.
- Keep stencils regular; minimize branching at boundaries (handle boundaries in separate kernels).
- For wide stencils, consider tiling strategies to improve cache locality.

See: `domains/fd.md`

### FFT-like spectral methods
- Taichi is great for custom kernels, but it is not a full replacement for vendor FFT libraries.
- If production FFT performance is required, prefer interoperability (CuPy/cuFFT) and keep Taichi for the non-FFT parts.
- If implementing FFT in Taichi:
  - use Stockham autosort (avoids bit-reversal pass)
  - represent complex as `ti.Vector([re, im])`
  - focus on coalesced loads/stores and minimizing global passes

See: `domains/fft.md` and `references/interop.md`

### MPM (P2G / grid / G2P)
- Classic structure:
  1) clear grid
  2) P2G scatter (watch atomic contention)
  3) grid update (forces, BCs)
  4) G2P gather
- Use quadratic B-spline weights with compile-time unrolled loops (`ti.static range(3)` per axis).
- Grid clearing should be efficient and separate (don’t mix with P2G).
- Tune `block_dim` on the hot loops; MPM can gain a lot from proper launch sizing.

See: `domains/mpm.md`

## Gotchas (must remember)
- First kernel call includes JIT compilation cost. Warm up before benchmarking.
- Python-side loops inside a “simulation step” kill performance. Push work into kernels.
- Branch-heavy kernels underperform on GPU. Separate boundary handling.
- `ti.ndarray` vs `ti.field`: use the right tool; some Taichi optimizations apply only to fields.
- Race conditions: any scatter update needs atomics or a safe alternative.
- Determinism: atomics can change floating-point summation order; build tests accordingly.

See: `references/gotchas.md`

## What to output when asked for code
When generating Taichi code, always include:
- `ti.init(...)` with explicit arch choice
- data definitions (fields/SNodes) with a short rationale
- kernels with clear separation of passes
- notes on tuning knobs (`block_dim`, precision, atomics, buffering)
- a minimal validation snippet (sanity checks)

## References in this Skill
- Performance: `references/performance.md`
- SNode/data layout: `references/data-layout-and-snode.md`
- Kernel patterns: `references/kernel-patterns.md`
- Gotchas: `references/gotchas.md`
- Interop (CuPy/Torch/etc.): `references/interop.md`
- Domain guides: `domains/*.md`