# FD (Finite Difference) — Taichi GPU Playbook

This domain guide describes how we structure finite difference (FD) methods in Taichi, with emphasis on:
- Stencil-based discretization for PDEs (heat, wave, diffusion, advection)
- Double-buffering strategies for time-stepping
- GPU-friendly boundary condition handling
- CFL stability considerations

Authoritative conventions:
- Grid indexing: `[i, j, k]` or `[i, j]` for 2D/3D structured grids
- Double-buffering: `u_old` and `u_new` to avoid race conditions
- Stencil patterns: 5-point (2D), 7-point (3D) for Laplacian
- Time-stepping: Explicit forward Euler, RK2/RK4, or semi-implicit schemes

(See `references/kernel-patterns.md` and `references/numerical-safeguards.md`.)

---

## 1) FD data model (what lives where)

### Grid fields
Store field data in multi-dimensional `ti.field`:
- `u_old[i, j, k]`: field values at time `t_n`
- `u_new[i, j, k]`: field values at time `t_{n+1}`
- Boundary conditions stored separately or as masks

### Domain parameters
- Grid spacing: `dx`, `dy`, `dz`
- Time step: `dt` (constrained by CFL condition)
- Domain extents: `nx`, `ny`, `nz`

### Double-buffering rationale
Never read and write the same field in parallel kernels. Always:
- Read from `u_old`
- Write to `u_new`
- Swap after each timestep

---

## 2) Kernel structure (GPU-friendly stencil patterns)

### Recommended per-step passes
1. **Interior update** (apply stencil to interior points)
2. **Boundary update** (handle edges/faces separately)
3. **Buffer swap** (`u_old, u_new = u_new, u_old` in Python scope)

### Example: 2D heat equation kernel

```python
@ti.kernel
def heat_step_2d(u_old: ti.template(), u_new: ti.template(),
                  dt: ti.f32, dx: ti.f32, alpha: ti.f32):
    """
    Explicit forward Euler for 2D heat equation: ∂u/∂t = α ∇²u

    Inputs:
        u_old: field at time t_n
        u_new: field at time t_{n+1} (output)
        dt: time step
        dx: grid spacing (assuming dx = dy)
        alpha: thermal diffusivity
    """
    r = alpha * dt / (dx * dx)  # CFL parameter

    # Interior points only (boundaries handled separately)
    for i, j in ti.ndrange((1, u_old.shape[0]-1), (1, u_old.shape[1]-1)):
        laplacian = (u_old[i+1, j] + u_old[i-1, j] +
                     u_old[i, j+1] + u_old[i, j-1] - 4.0 * u_old[i, j])
        u_new[i, j] = u_old[i, j] + r * laplacian
```

**Stability:** For forward Euler, require `r = α * dt / dx² ≤ 0.25` (2D) or `≤ 1/6` (3D).

---

## 3) Stencil patterns (common discretizations)

### Laplacian (2nd derivative)
**5-point stencil (2D):**
```
    [0, +1]
[-1, 0] [0, 0] [+1, 0]
    [0, -1]
```
∇²u ≈ (u[i+1,j] + u[i-1,j] + u[i,j+1] + u[i,j-1] - 4u[i,j]) / dx²

**7-point stencil (3D):**
Add `[i,j,k±1]` terms, coefficient becomes -6 at center.

### Gradient (1st derivative, centered difference)
∂u/∂x ≈ (u[i+1,j] - u[i-1,j]) / (2*dx)

### Upwind scheme (advection)
For advection equation ∂u/∂t + c ∂u/∂x = 0:
- If c > 0: use backward difference (u[i] - u[i-1]) / dx
- If c < 0: use forward difference (u[i+1] - u[i]) / dx

---

## 4) Boundary conditions (separate kernels recommended)

### Dirichlet (fixed value)
```python
@ti.kernel
def apply_dirichlet_bc(u: ti.template(), value: ti.f32):
    # Left and right boundaries
    for j in range(u.shape[1]):
        u[0, j] = value
        u[u.shape[0]-1, j] = value
    # Top and bottom boundaries
    for i in range(u.shape[0]):
        u[i, 0] = value
        u[i, u.shape[1]-1] = value
```

### Neumann (fixed gradient, e.g., ∂u/∂n = 0)
```python
@ti.kernel
def apply_neumann_bc(u: ti.template()):
    # Zero gradient at boundaries (copy interior values)
    for j in range(u.shape[1]):
        u[0, j] = u[1, j]  # Left boundary
        u[u.shape[0]-1, j] = u[u.shape[0]-2, j]  # Right
    for i in range(u.shape[0]):
        u[i, 0] = u[i, 1]  # Bottom
        u[i, u.shape[1]-1] = u[i, u.shape[1]-2]  # Top
```

### Periodic boundaries
Handled via index wrapping:
```python
i_left = (i - 1 + nx) % nx
i_right = (i + 1) % nx
```

**Performance note:** Separate boundary kernels avoid thread divergence in interior update kernel.

---

## 5) Time integration schemes

### Forward Euler (1st order)
```
u^{n+1} = u^n + dt * RHS(u^n)
```
- Simplest, but requires small dt for stability
- Stability region: CFL constraints apply

### RK2 (2nd order, midpoint method)
```python
@ti.kernel
def rk2_step(u_old: ti.template(), u_new: ti.template(),
             u_tmp: ti.template(), dt: ti.f32):
    # Stage 1: compute k1 = RHS(u_old)
    compute_rhs(u_old, k1)

    # Stage 2: u_tmp = u_old + 0.5 * dt * k1
    for I in ti.grouped(u_old):
        u_tmp[I] = u_old[I] + 0.5 * dt * k1[I]

    # Stage 3: compute k2 = RHS(u_tmp)
    compute_rhs(u_tmp, k2)

    # Final: u_new = u_old + dt * k2
    for I in ti.grouped(u_old):
        u_new[I] = u_old[I] + dt * k2[I]
```

### Semi-implicit (for diffusion)
Treat diffusion term implicitly to remove CFL constraint:
- Solve `(I - α * dt * ∇²) u^{n+1} = u^n` using iterative solver
- See `domains/linear-solvers.md` for CG/Jacobi/Gauss-Seidel

---

## 6) CFL stability conditions

### Explicit diffusion
α * dt / dx² ≤ C_max
- 1D: C_max = 0.5
- 2D: C_max = 0.25
- 3D: C_max = 1/6

### Advection (upwind)
|c| * dt / dx ≤ 1

### Wave equation (∂²u/∂t² = c² ∇²u)
c * dt / dx ≤ 1 / √d (d = dimension)

**Validation:** Always check CFL at initialization and log warnings if violated.

```python
def check_cfl_diffusion(alpha, dt, dx, dim):
    cfl = alpha * dt / (dx * dx)
    cfl_max = {1: 0.5, 2: 0.25, 3: 1.0/6.0}[dim]
    if cfl > cfl_max:
        print(f"WARNING: CFL = {cfl:.3f} > {cfl_max:.3f}, unstable!")
    return cfl <= cfl_max
```

---

## 7) Example: 2D wave equation

```python
import taichi as ti
ti.init(arch=ti.gpu)

nx, ny = 512, 512
dx = 1.0 / nx
dt = 0.4 * dx  # CFL: c * dt / dx ≤ 1 for c = 1

u = ti.field(ti.f32, shape=(nx, ny))       # displacement
v = ti.field(ti.f32, shape=(nx, ny))       # velocity
u_new = ti.field(ti.f32, shape=(nx, ny))

@ti.kernel
def wave_step():
    """Wave equation: ∂²u/∂t² = ∇²u (c = 1)"""
    c_sq = 1.0
    r = c_sq * dt * dt / (dx * dx)

    for i, j in ti.ndrange((1, nx-1), (1, ny-1)):
        laplacian = (u[i+1, j] + u[i-1, j] + u[i, j+1] + u[i, j-1] - 4*u[i, j])
        u_new[i, j] = 2*u[i, j] - u_prev[i, j] + r * laplacian

# Timestep loop
for step in range(num_steps):
    wave_step()
    apply_neumann_bc(u_new)
    u_prev.copy_from(u)
    u.copy_from(u_new)
```

---

## 8) GPU performance notes

### Memory access patterns
- Stencils have good spatial locality (neighboring reads)
- Ensure fields are allocated contiguously: `ti.field(..., shape=(nx, ny))`
- Use `ti.grouped(field)` for dimension-agnostic indexing

### Loop unrolling
For small fixed stencils, use `ti.static` to unroll:
```python
@ti.kernel
def laplacian_unrolled():
    for i, j in u:
        result = 0.0
        for di, dj in ti.static(ti.ndrange((-1, 2), (-1, 2))):
            if di == 0 and dj == 0:
                result -= 4.0 * u[i, j]
            else:
                result += u[i+di, j+dj]
        laplacian[i, j] = result / (dx * dx)
```

### Block dimensions
For 2D/3D grids, tune `block_dim` for cache efficiency:
```python
@ti.kernel
def update_field():
    ti.loop_config(block_dim=256)  # Tune for GPU warp size
    for i, j in u:
        # ... stencil computation
```

---

## 9) Common pitfalls (gotchas)

### Reading and writing same field
❌ **WRONG:**
```python
for i, j in u:
    u[i, j] = (u[i+1, j] + u[i-1, j]) / 2  # Race condition!
```

✓ **CORRECT:**
```python
for i, j in u_old:
    u_new[i, j] = (u_old[i+1, j] + u_old[i-1, j]) / 2
```

### Boundary indexing out of bounds
Always use interior ranges `(1, n-1)` or add bounds checks.

### CFL violation
Silent instability! Always validate CFL before running.

---

## 10) Validation (FD sanity checks)

Minimum tests:
- **Constant solution:** If initial condition is uniform, it should remain so
- **Symmetry:** Symmetric initial conditions should preserve symmetry
- **Conservation:** For conservative schemes (e.g., advection), check total mass
- **Convergence:** Refine grid (dx → dx/2), verify error decreases at expected rate
- **Energy stability:** For wave equation, total energy E = ∫(u² + |∇u|²) should be conserved

### Example convergence test
```python
def test_convergence_heat_equation():
    """Test spatial convergence: error ~ O(dx²)"""
    errors = []
    for nx in [32, 64, 128, 256]:
        dx = 1.0 / nx
        dt = 0.1 * dx * dx  # Safe CFL
        error = run_simulation(nx, dt)
        errors.append(error)

    # Check that error halves when dx is halved (2nd order)
    ratio = errors[0] / errors[1]
    assert 3.5 < ratio < 4.5, f"Expected ~4x reduction, got {ratio}"
```

---

## 11) References and further reading

- `references/kernel-patterns.md` - Loop patterns and optimization
- `references/numerical-safeguards.md` - Stability and validation strategies
- `references/performance.md` - GPU profiling and tuning
- `domains/linear-solvers.md` - Implicit schemes and iterative solvers
- `domains/time-integration.md` - Advanced time-stepping methods

For theoretical background:
- LeVeque, "Finite Difference Methods for Ordinary and Partial Differential Equations"
- Strikwerda, "Finite Difference Schemes and Partial Differential Equations"
