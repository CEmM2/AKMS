# Review Checklist for Taichi Simulations

Use this checklist to systematically review code. Not all items apply to every PR, but this serves as a baseline.

## 1. Correctness (The Prime Directive)
- [ ] **Physical Laws**: Does the code respect conservation laws (mass, momentum, energy)?
- [ ] **Sign Conventions**:
    - [ ] Voigt Order: `[xx, yy, zz, xy, xz, yz]`?
    - [ ] Pressure: Compression Positive? (`p = -mean(σ)`)
    - [ ] Stress: Updates in Corotational Frame?
- [ ] **Invariants**: Are invariants preserved? (e.g., `det(F) > 0` for solids).
- [ ] **Math**: Are tensor operations correct? (Check against SymPy or reference if complex).

## 2. Performance & Taichi Patterns
- [ ] **Arch**: Is `ti.init(arch=...)` explicit?
- [ ] **Hot Loops**: Are all heavy loops inside `@ti.kernel`?
- [ ] **Python Loops**: Are Python-side loops over elements/particles avoided?
- [ ] **Data Layout**:
    - [ ] Struct-of-Arrays (SoA) for large fields?
    - [ ] `ti.Vector/Matrix` for small fixed state?
    - [ ] `ti.static` used for small unrolling (not large loops)?
- [ ] **Atomics**:
    - [ ] Minimized in hot loops?
    - [ ] Safe (no race conditions)?
    - [ ] Deterministic where required?
- [ ] **Kernels**:
    - [ ] Separate passes for Clear / Compute / Scatter / Gather?
    - [ ] Block dim tuned (or at least `ti.loop_config` present for hotspots)?

## 3. Style & Architecture
- [ ] **Naming**:
    - [ ] Tensors: `F`, `C`, `sigma`, etc. (See `taichi-gpu-sim` style).
    - [ ] Kernels: Descriptive names?
- [ ] **Data Ownership**:
    - [ ] Clear owner for every buffer (Field vs Ndarray vs Torch)?
    - [ ] No unnecessary copying (GPU -> CPU -> GPU)?
- [ ] **Modularity**:
    - [ ] Is domain logic (constitutive, BCs) separated from core solvers?

## 4. Documentation
- [ ] **Docstrings**: Does every kernel explain *what* it does and *inputs/outputs*?
- [ ] **Complexity**: Are non-obvious math steps explained with comments?
- [ ] **Tuning**: Are `block_dim` choices or magic numbers explained?

## 5. Testing
- [ ] **Unit Tests**: Are small helper functions tested?
- [ ] **Regression**: Do existing tests pass?
- [ ] **New Tests**: Is there a test case for the new feature/fix?

## 6. Domain Specifics
### FEM
- [ ] Matrix-free for large problems?
- [ ] Assembly uses minimal atomics?
- [ ] Quadrature weights precomputed?

### MPM
- [ ] Grid clearing separate from P2G?
- [ ] B-spline weights unrolled?
- [ ] P2G/G2P optimized loops?

### FD
- [ ] Double buffering (`u_old`, `u_new`) used?
- [ ] Boundaries handled separately?
