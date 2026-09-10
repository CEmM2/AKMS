# MPM (Material Point Method) — Taichi GPU Playbook

This domain guide describes how we structure MPM in Taichi, with emphasis on:
- Particle-to-grid (P2G) and grid-to-particle (G2P) transfers
- B-spline interpolation weights and gradients
- APIC (Affine Particle-In-Cell) for reduced numerical dissipation
- GPU-friendly atomic scatter patterns

Authoritative conventions:
- **Grid clear → P2G → Grid update → G2P** pipeline (4 distinct kernels)
- Stress/deformation stored on particles
- Velocities/forces computed on grid
- B-spline kernels: Linear, quadratic, or cubic (quadratic is standard)
- Atomic operations minimized via careful kernel design

(See `references/kernel-patterns.md`, `references/data-layout-and-snode.md`, and `references/performance.md`.)

---

## 1) MPM data model (what lives where)

### Particle data (Lagrangian)
Store per-particle state in struct-of-arrays (SoA):
```python
n_particles = 10000
x = ti.Vector.field(3, ti.f32, shape=n_particles)  # Position
v = ti.Vector.field(3, ti.f32, shape=n_particles)  # Velocity
C = ti.Matrix.field(3, 3, ti.f32, shape=n_particles)  # APIC affine matrix
F = ti.Matrix.field(3, 3, ti.f32, shape=n_particles)  # Deformation gradient
J = ti.field(ti.f32, shape=n_particles)  # Determinant of F
mass = ti.field(ti.f32, shape=n_particles)  # Particle mass
```

### Grid data (Eulerian, temporary)
Grid is cleared and rebuilt every timestep:
```python
grid_res = 128
grid_v = ti.Vector.field(3, ti.f32, shape=(grid_res, grid_res, grid_res))
grid_m = ti.field(ti.f32, shape=(grid_res, grid_res, grid_res))
```

**Key insight:** Grid data is transient. Only particle data persists across timesteps.

---

## 2) MPM pipeline (canonical 4-kernel structure)

### Timestep structure
```python
def mpm_step(dt):
    clear_grid()      # Kernel 1: Zero out grid
    p2g(dt)           # Kernel 2: Particle → Grid transfer
    grid_update(dt)   # Kernel 3: Grid momentum update + BCs
    g2p(dt)           # Kernel 4: Grid → Particle transfer
```

### Why separate kernels?
- **Clear grid:** Parallel write, no atomics
- **P2G:** Atomic scatter to grid (particles → grid nodes)
- **Grid update:** Parallel over grid nodes, no race conditions
- **G2P:** Gather from grid (grid nodes → particles), no atomics

**Performance:** Keep each pass simple and data-parallel.

---

## 3) Interpolation weights (B-spline kernels)

### Quadratic B-spline (standard choice)
For a particle at position `xp`, influencing grid node `i`:
```python
@ti.func
def quadratic_kernel(x: ti.f32) -> ti.f32:
    """Quadratic B-spline weight"""
    abs_x = abs(x)
    if abs_x < 0.5:
        return 0.75 - abs_x * abs_x
    elif abs_x < 1.5:
        return 0.5 * (1.5 - abs_x) ** 2
    else:
        return 0.0

@ti.func
def quadratic_kernel_grad(x: ti.f32) -> ti.f32:
    """Derivative of quadratic B-spline"""
    if abs(x) < 0.5:
        return -2.0 * x
    elif x >= 0.5 and x < 1.5:
        return x - 1.5
    elif x <= -0.5 and x > -1.5:
        return x + 1.5
    else:
        return 0.0
```

### Weight computation (per particle)
```python
@ti.func
def compute_weights_2d(xp: ti.template(), base: ti.template()):
    """
    Compute B-spline weights for 2D grid.
    Returns: weights[3, 3], gradients[3, 3, 2]
    """
    fx = xp - base  # Fractional position relative to base node

    w = ti.Matrix.zero(ti.f32, 3, 3)
    dw = ti.Matrix.zero(ti.f32, 3, 3, 2)

    for i, j in ti.static(ti.ndrange(3, 3)):
        offset = ti.Vector([i, j]) - 1  # -1, 0, +1
        w[i, j] = quadratic_kernel(fx[0] - offset[0]) * quadratic_kernel(fx[1] - offset[1])

        dw[i, j, 0] = quadratic_kernel_grad(fx[0] - offset[0]) * quadratic_kernel(fx[1] - offset[1])
        dw[i, j, 1] = quadratic_kernel(fx[0] - offset[0]) * quadratic_kernel_grad(fx[1] - offset[1])

    return w, dw
```

**Stencil size:** Quadratic B-spline uses 3×3 (2D) or 3×3×3 (3D) grid nodes per particle.

---

## 4) Particle-to-Grid (P2G) transfer

### Goal
Transfer particle mass, momentum, and forces to grid.

### Kernel structure
```python
@ti.kernel
def p2g(dt: ti.f32):
    """Particle to Grid: scatter particle state to grid"""
    for p in range(n_particles):
        # Particle state
        xp = x[p]
        vp = v[p]
        Cp = C[p]  # APIC affine velocity field
        Fp = F[p]
        mp = mass[p]

        # Stress computation (constitutive model)
        stress = compute_stress(Fp)  # Returns Cauchy stress or PK1

        # Grid cell and fractional position
        base = ti.cast(xp * inv_dx - 0.5, ti.i32)
        fx = xp * inv_dx - base

        # B-spline weights
        w, dw = compute_weights_2d(fx, base)

        # Scatter to 3×3 neighborhood
        for i, j in ti.static(ti.ndrange(3, 3)):
            offset = ti.Vector([i, j]) - 1
            grid_idx = base + offset
            weight = w[i, j]
            dweight = ti.Vector([dw[i, j, 0], dw[i, j, 1]])

            # APIC momentum transfer
            grid_v_p = vp + Cp @ (offset * dx - (xp - base * dx))

            # Scatter mass and momentum
            grid_m[grid_idx] += weight * mp
            grid_v[grid_idx] += weight * mp * grid_v_p

            # Scatter forces (from stress divergence)
            force = -dt * 4 * inv_dx * inv_dx * stress @ dweight * dx * dx
            grid_v[grid_idx] += force
```

**Key points:**
- Use `ti.atomic_add()` implicitly (Taichi handles this for `+=` on grid fields)
- Unroll 3×3 or 3×3×3 loop with `ti.static`
- Compute stress on-the-fly (avoid storing 6 components per particle if possible)

---

## 5) Grid operations (momentum update + boundary conditions)

### Kernel structure
```python
@ti.kernel
def grid_update(dt: ti.f32, gravity: ti.f32):
    """Update grid momenta and apply boundary conditions"""
    for i, j in grid_m:
        if grid_m[i, j] > 0:
            # Normalize momentum by mass
            grid_v[i, j] /= grid_m[i, j]

            # Apply gravity
            grid_v[i, j][1] -= dt * gravity

            # Boundary conditions (sticky walls)
            if i < 3 or i > grid_res - 3:
                grid_v[i, j] = ti.Vector([0.0, 0.0])
            if j < 3 or j > grid_res - 3:
                grid_v[i, j] = ti.Vector([0.0, 0.0])

            # Alternative: Separate velocity (slip vs stick)
            # if i < 3: grid_v[i, j][0] = 0  # No horizontal velocity at left wall
```

**No race conditions:** Each grid node updated independently.

---

## 6) Grid-to-Particle (G2P) transfer

### Goal
Interpolate grid velocities back to particles and update particle state.

### Kernel structure
```python
@ti.kernel
def g2p(dt: ti.f32):
    """Grid to Particle: gather grid velocities and update particles"""
    for p in range(n_particles):
        xp = x[p]
        base = ti.cast(xp * inv_dx - 0.5, ti.i32)
        fx = xp * inv_dx - base

        w, dw = compute_weights_2d(fx, base)

        # Gather velocity and affine matrix
        new_v = ti.Vector.zero(ti.f32, 2)
        new_C = ti.Matrix.zero(ti.f32, 2, 2)

        for i, j in ti.static(ti.ndrange(3, 3)):
            offset = ti.Vector([i, j]) - 1
            grid_idx = base + offset
            weight = w[i, j]
            dweight = ti.Vector([dw[i, j, 0], dw[i, j, 1]])

            grid_v_ij = grid_v[grid_idx]

            # APIC: gather velocity
            new_v += weight * grid_v_ij

            # APIC: gather affine velocity gradient
            new_C += 4 * inv_dx * weight * grid_v_ij.outer_product(offset * dx)

        # Update particle velocity and affine matrix
        v[p] = new_v
        C[p] = new_C

        # Advect particle position
        x[p] += dt * new_v

        # Update deformation gradient (elastic/plastic)
        grad_v = new_C
        F[p] = (ti.Matrix.identity(ti.f32, 2) + dt * grad_v) @ F[p]
        J[p] = F[p].determinant()
```

**Key points:**
- Gather operation (read from grid, write to particles) — no atomics needed
- APIC transfers affine velocity field to reduce dissipation
- Deformation gradient updated incrementally

---

## 7) Constitutive models (stress computation)

### Neo-Hookean (hyperelastic)
```python
@ti.func
def compute_stress_neohookean(F: ti.template(), mu: ti.f32, lambda_: ti.f32):
    """
    Neo-Hookean stress (Cauchy, 2D plane strain)
    σ = (μ/J)(F F^T - I) + (λ/J) ln(J) I
    """
    J = F.determinant()
    F_inv_T = F.inverse().transpose()

    sigma = (mu / J) * (F @ F.transpose() - ti.Matrix.identity(ti.f32, 2))
    sigma += (lambda_ / J) * ti.log(J) * ti.Matrix.identity(ti.f32, 2)

    return sigma
```

### Fixed-Corotated (common in graphics)
```python
@ti.func
def compute_stress_fixed_corotated(F: ti.template(), mu: ti.f32, lambda_: ti.f32):
    """
    Fixed-corotated elasticity (1st PK stress)
    P = 2μ(F - R) + λ(J - 1)J R
    where R from polar decomposition F = RS
    """
    J = F.determinant()
    R, S = polar_decompose(F)  # See below

    P = 2 * mu * (F - R) + lambda_ * (J - 1) * J * R
    return P
```

### Polar decomposition (SVD-based)
```python
@ti.func
def polar_decompose(F: ti.template()):
    """F = RS via SVD: F = U Σ V^T, then R = U V^T"""
    U, sig, V = ti.svd(F)
    R = U @ V.transpose()
    S = V @ ti.Matrix.diag(2, sig) @ V.transpose()
    return R, S
```

---

## 8) Plasticity (von Mises / Drucker-Prager)

### Yield condition and return mapping
```python
@ti.func
def apply_plasticity(F: ti.template(), yield_stress: ti.f32):
    """
    Simple von Mises plasticity with return mapping.
    If stress exceeds yield, scale F to satisfy yield surface.
    """
    U, sig, V = ti.svd(F)
    eps = ti.log(sig)  # Logarithmic strain
    eps_dev = eps - eps.sum() / 3.0  # Deviatoric part
    eps_norm = eps_dev.norm()

    if eps_norm > yield_stress:
        eps_dev *= yield_stress / eps_norm  # Scale back to yield surface

    eps_new = eps_dev + eps.sum() / 3.0
    sig_new = ti.exp(eps_new)
    F_new = U @ ti.Matrix.diag(2, sig_new) @ V.transpose()

    return F_new
```

Apply plasticity in G2P after updating `F[p]`.

---

## 9) GPU performance optimization

### Atomic operation minimization
- P2G requires atomics (unavoidable for scatter)
- But: unroll loops with `ti.static` to reduce overhead
- Consider using `ti.atomic_add()` explicitly if needed

### Memory layout
- Prefer SoA: `x = ti.Vector.field(3, f32, shape=n)` over AoS
- Keep particle count as multiple of warp size (32 or 64)

### Grid resolution tuning
- Too fine: Wasted memory and bandwidth
- Too coarse: Poor spatial resolution, large stencils
- Rule of thumb: 2-4 particles per grid cell

### Profiling hotspots
Typical breakdown:
- P2G: 40-50% (stress computation + scatter)
- G2P: 30-40% (gather + F update)
- Grid ops: 10-20%

Use Taichi's built-in profiler:
```python
ti.profiler.print_kernel_profiler_info()
```

---

## 10) Boundary conditions

### Sticky walls (no-slip)
```python
if i < bound or i >= grid_res - bound:
    grid_v[i, j] = ti.Vector.zero(ti.f32, 2)
```

### Slip walls (no normal velocity)
```python
if i < bound:
    grid_v[i, j][0] = 0  # Zero x-velocity at left wall
if j < bound:
    grid_v[i, j][1] = 0  # Zero y-velocity at bottom wall
```

### Free boundaries (do nothing)
Particles can leave domain (or reflect them in G2P).

### Collision objects
Check particle position in G2P, apply penalty forces or projection.

---

## 11) Example: 2D elastic collision

```python
import taichi as ti

ti.init(arch=ti.gpu)

# Grid parameters
grid_res = 64
dx = 1.0 / grid_res
inv_dx = 1.0 / dx

# Particle parameters
n_particles = 1000
x = ti.Vector.field(2, ti.f32, shape=n_particles)
v = ti.Vector.field(2, ti.f32, shape=n_particles)
C = ti.Matrix.field(2, 2, ti.f32, shape=n_particles)
F = ti.Matrix.field(2, 2, ti.f32, shape=n_particles)
mass = ti.field(ti.f32, shape=n_particles)

# Grid fields
grid_v = ti.Vector.field(2, ti.f32, shape=(grid_res, grid_res))
grid_m = ti.field(ti.f32, shape=(grid_res, grid_res))

# Material properties
E, nu = 1e4, 0.2  # Young's modulus, Poisson's ratio
mu = E / (2 * (1 + nu))
lambda_ = E * nu / ((1 + nu) * (1 - 2 * nu))

@ti.kernel
def clear_grid():
    for i, j in grid_m:
        grid_m[i, j] = 0.0
        grid_v[i, j] = ti.Vector([0.0, 0.0])

@ti.kernel
def p2g(dt: ti.f32):
    for p in x:
        base = ti.cast(x[p] * inv_dx - 0.5, ti.i32)
        fx = x[p] * inv_dx - base

        # Stress (Neo-Hookean)
        J = F[p].determinant()
        F_inv_T = F[p].inverse().transpose()
        stress = mu * (F[p] @ F[p].transpose() - ti.Matrix.identity(ti.f32, 2)) / J
        stress += lambda_ * ti.log(J) / J * ti.Matrix.identity(ti.f32, 2)
        stress *= -dt * 4 * inv_dx * inv_dx

        # Scatter to grid (simplified, no B-spline shown for brevity)
        # ... (use quadratic_kernel as shown above)

@ti.kernel
def grid_update(dt: ti.f32):
    for i, j in grid_m:
        if grid_m[i, j] > 0:
            grid_v[i, j] /= grid_m[i, j]
            grid_v[i, j][1] -= dt * 9.8  # Gravity

            # Boundary conditions
            if i < 3 or i > grid_res - 3 or j < 3 or j > grid_res - 3:
                grid_v[i, j] = ti.Vector([0.0, 0.0])

@ti.kernel
def g2p(dt: ti.f32):
    for p in x:
        # ... (gather velocity, update C, F, x as shown above)
        pass

# Initialize particles
@ti.kernel
def init_particles():
    for p in x:
        x[p] = [ti.random() * 0.4 + 0.3, ti.random() * 0.4 + 0.3]
        v[p] = [0.0, -1.0]
        F[p] = ti.Matrix.identity(ti.f32, 2)
        C[p] = ti.Matrix.zero(ti.f32, 2, 2)
        mass[p] = 1.0

init_particles()

# Main loop
dt = 1e-4
for step in range(5000):
    clear_grid()
    p2g(dt)
    grid_update(dt)
    g2p(dt)
```

---

## 12) Variants and extensions

### MLS-MPM (Moving Least Squares MPM)
- Improves accuracy near boundaries
- Slightly more expensive (polynomial basis)
- Reference: Hu et al., "A Moving Least Squares Material Point Method" (2018)

### CPIC (Compatible Particle-In-Cell)
- Alternative to APIC with better momentum conservation
- Reference: Fu et al., "A Polynomial Particle-In-Cell Method" (2017)

### Implicit MPM
- Use grid velocities implicitly for stiff materials
- Requires linear solve at grid level

---

## 13) Common pitfalls (gotchas)

### Forgetting to clear grid
❌ **WRONG:** Accumulating into uncleaned grid from previous timestep
✓ **CORRECT:** Always `clear_grid()` at start of timestep

### Atomic race conditions
When scattering to grid, ensure atomics are used (Taichi handles `+=` automatically for fields).

### Wrong B-spline gradient sign
Check that gradient formulas match your coordinate system.

### Particle escape
Particles can leave domain if no boundary handling in G2P. Either clamp positions or use collision detection.

### Timestep too large
MPM stability depends on CFL: `dt < dx / max(|v|)`. Start with small dt and increase cautiously.

---

## 14) Validation (MPM sanity checks)

Minimum tests:
- **Free fall:** Particles under gravity should accelerate at g
- **Rigid translation:** Moving rigid body should not deform (F = I)
- **Elastic bounce:** Sphere dropped on floor should bounce to ~original height (energy conservation)
- **Plastic flow:** Exceeding yield stress should cause permanent deformation
- **Conservation:** Total momentum conserved in absence of external forces

### Example: Energy conservation test
```python
def compute_kinetic_energy():
    ke = 0.0
    for p in range(n_particles):
        ke += 0.5 * mass[p] * v[p].norm_sqr()
    return ke

# Check energy conservation for elastic collision (no dissipation)
E0 = compute_kinetic_energy() + compute_potential_energy()
# ... run simulation
E1 = compute_kinetic_energy() + compute_potential_energy()
assert abs(E1 - E0) / E0 < 0.01, "Energy not conserved!"
```

---

## 15) References and further reading

- `references/kernel-patterns.md` - Loop unrolling and atomic patterns
- `references/data-layout-and-snode.md` - SoA vs AoS performance
- `references/performance.md` - GPU profiling and optimization
- `domains/fem.md` - Comparison with mesh-based FEM
- `references/stress-integration.md` - Constitutive models and stress updates

For theoretical background:
- Sulsky et al., "A particle method for history-dependent materials" (1994) — Original MPM paper
- Jiang et al., "The Affine Particle-In-Cell Method" (2015) — APIC
- Hu et al., "A Moving Least Squares Material Point Method with Displacement Discontinuity and Two-Way Rigid Body Coupling" (2018) — MLS-MPM
- Stomakhin et al., "A material point method for snow simulation" (2013) — Influential graphics paper

### Taichi MPM examples
- Official Taichi examples: https://github.com/taichi-dev/taichi/tree/master/python/taichi/examples
- MLS-MPM 88 lines: https://github.com/yuanming-hu/taichi_mpm
