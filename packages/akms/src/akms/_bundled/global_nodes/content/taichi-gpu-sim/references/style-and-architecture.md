# Style & Architecture — making the codebase coherent and fast

This doc defines “house style” so generated Taichi code matches the repo’s structure and stays maintainable.

---

## 1) Naming conventions (consistency beats clever)

### Tensors (3×3)
- `F`: deformation gradient
- `C`: right Cauchy–Green
- `b`: left Cauchy–Green
- `L`: velocity gradient
- `D`: symmetric part of L
- `W`: skew part of L
- `R_delta`: Hughes–Winget incremental rotation
- `R_half`: half-step rotation

### Stress (Voigt)
- `sigma_v`: tensorial Voigt `[xx,yy,zz,xy,xz,yz]`
- `sigma_hat_v`: corotational-frame stress (Voigt)
- `s_dev`: deviatoric 3×3 tensor
- `p`: pressure (compression positive)
- `m`: mean stress (tension positive)
- `vm`: von Mises equivalent stress

### State scalars
- `peeq`: equivalent plastic strain
- `peeq_dot`: plastic strain rate
- `T`: temperature
- `ws`: ω_s damage scalar
- `wt`: ω_t damage scalar

---

## 2) File layout (where things live)

### `reference/*`
Cross-domain rules:
- performance, data layout, gotchas, safeguards, conventions

### `domains/*`
Domain recipes and patterns:
- `fem.md`, `mpm.md`, `fd.md`, `fft.md`
- domain-specific constitutive notes where needed

### Code organization (recommended)
- `kinematics.py`: rotation, Voigt pack/unpack, tangent rotation
- `constitutive.py`: `Stress_Update6` and material models
- `fem_ops.py`: kinematics, internal force, operator apply
- `solvers.py`: CG/PCG kernels and reductions
- `bc.py`: boundary kernels
- `utils_debug.py`: scans, flags, counters

---

## 3) Data ownership rules (stop copying data for sport)

### Choose one “owner” per major buffer:
- Taichi `field` for layout-tuned core state
- Taichi `ndarray` for contiguous dense buffers and AOT
- Torch tensor when you want a Torch-driven pipeline and Taichi kernels as operators

Do not bounce state:
- GPU → CPU → GPU every step
- field → torch → field every step
unless you’re deliberately benchmarking PCIe.

---

## 4) Kernel pass boundaries (recommended)
Prefer explicit passes:
1. clear / reset
2. compute (map)
3. scatter
4. normalize / enforce constraints
5. gather
6. diagnostics (infrequent)

Avoid:
- mixing boundary handling into interior compute kernels
- mixing diagnostics and IO into step kernels

---

## 5) Taichi code style rules

### Always define arch explicitly
- `ti.init(arch=ti.cuda)` (or appropriate GPU arch)

### Use `ti.loop_config(block_dim=...)` only on hotspots
- place immediately before the hot loop
- tune after profiling

### `ti.static` usage
- ok for small fixed loops (3, 4, 8, 27)
- never for big loops

### Avoid Python-side per-element logic
- no Python loops over elements/nodes in the hot path

---

## 6) “Contracts” that generated code must follow (hard rules)

1) Tensorial Voigt order is `[xx, yy, zz, xy, xz, yz]`, no shear scaling.
2) Stress update happens in corotational frame; rotate in/out via Hughes–Winget.
3) Pressure sign convention: compression-positive pressure `p = -mean(σ)`.
4) EOS tensile-only gate triggers when `p_EOS < 0`.
5) Tangent rotation uses Mandel-space transforms; no naive 3×3 rotation of 6×6 tangents.

If code violates these, it’s wrong even if it compiles and “looks right.”

---

## 7) Minimal documentation per kernel/function
Every performance-critical kernel should have:
- purpose (1 sentence)
- inputs/outputs (fields and shapes)
- invariants (what must hold)
- tuning knobs (`block_dim`, precision, clamping policy)

This makes later optimization and debugging possible without archaeology.