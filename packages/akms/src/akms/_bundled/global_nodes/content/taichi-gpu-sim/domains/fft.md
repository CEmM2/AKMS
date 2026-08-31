# FFT (Spectral Methods) — Taichi GPU Playbook

This domain guide describes how we structure FFT-based spectral methods in Taichi, with emphasis on:
- Pseudo-spectral methods for PDEs (Navier-Stokes, phase-field, etc.)
- Interoperability with cuFFT and external FFT libraries
- Complex number representation in Taichi
- Spectral derivative computation and dealiasing

Authoritative conventions:
- FFT convention: Forward transform normalized by 1/N, inverse unnormalized (or vice versa, be consistent)
- Complex storage: `ti.Vector([real, imag])` or separate fields
- Wavenumber indexing: `[0, 1, ..., N/2-1, -N/2, ..., -1]` (NumPy/FFTW convention)
- Dealiasing: 2/3 rule or padding for nonlinear terms

(See `references/interop.md` for cuFFT/CuPy integration and `references/kernel-patterns.md` for complex arithmetic.)

---

## 1) FFT data model (what lives where)

### Real and Fourier space fields
For a real-valued field `u(x)`:
- **Physical space:** `u_real[i, j, k]` (ti.field of floats)
- **Fourier space:** `u_hat[i, j, k]` (complex, stored as `ti.Vector.field(2, ti.f32)` or via external library)

### Wavenumber grids
Precompute wavenumber arrays for spectral derivatives:
```python
# 1D example
kx = ti.field(ti.f32, shape=N)

@ti.kernel
def init_wavenumbers(N: ti.i32):
    for i in range(N):
        if i < N // 2:
            kx[i] = ti.f32(i)
        else:
            kx[i] = ti.f32(i - N)
```

### Storage considerations
- **R2C transforms:** Only need to store `N/2+1` complex coefficients due to conjugate symmetry
- **C2C transforms:** Full N complex coefficients
- Memory trade-off: In-place transforms save memory but may limit flexibility

---

## 2) FFT library interop (recommended approach)

### Option A: CuPy (easiest for NumPy users)
```python
import taichi as ti
import cupy as cp

ti.init(arch=ti.cuda)

# Taichi field
u = ti.field(ti.f32, shape=(N, N))

# Convert to CuPy for FFT
u_cupy = cp.asarray(u.to_numpy())
u_hat_cupy = cp.fft.fft2(u_cupy)

# Convert back to Taichi
u_hat = ti.Vector.field(2, ti.f32, shape=(N, N))
u_hat.from_numpy(cp.asnumpy(cp.stack([u_hat_cupy.real, u_hat_cupy.imag], axis=-1)))
```

**Pros:** Simple, familiar NumPy API
**Cons:** Host-device copy overhead (manageable for moderate-sized grids)

### Option B: cuFFT via Taichi interop (zero-copy)
Use `ti.types.ndarray` to pass GPU pointers directly to cuFFT (requires CUDA kernel interop):
```python
import pycuda.gpuarray as gpuarray
from skcuda import cufft

@ti.kernel
def get_device_ptr(field: ti.template()) -> ti.u64:
    return ti.uint64(field.get_device_ptr())

# Get Taichi field GPU pointer
ptr = get_device_ptr(u)
u_gpu = gpuarray.GPUArray((N, N), dtype=np.float32, gpudata=ptr)

# Create cuFFT plan and execute
plan = cufft.cufftPlan2d(N, N, cufft.CUFFT_R2C)
u_hat_gpu = gpuarray.zeros((N, N//2+1), dtype=np.complex64)
cufft.cufftExecR2C(plan, u_gpu.gpudata, u_hat_gpu.gpudata)
```

**Pros:** Zero-copy, maximum performance
**Cons:** More complex setup, requires CUDA interop knowledge

### Option C: Taichi-native FFT (experimental, limited)
Taichi has limited native FFT support. For production, prefer cuFFT/CuPy interop.

**Recommendation:** Use CuPy for prototyping, cuFFT for production performance-critical code.

---

## 3) Spectral derivatives (how to compute ∂u/∂x in Fourier space)

### Core identity
∂u/∂x ↔ i * kx * û(k)

```python
import taichi as ti

N = 256
u_hat = ti.Vector.field(2, ti.f32, shape=N)  # [real, imag]
dudx_hat = ti.Vector.field(2, ti.f32, shape=N)
kx = ti.field(ti.f32, shape=N)

@ti.kernel
def spectral_derivative_x():
    """Compute ∂u/∂x in Fourier space: multiply by i*kx"""
    for i in range(N):
        # û_hat[i] = [real, imag]
        # i * kx * (real + i*imag) = i*kx*real + i²*kx*imag
        #                          = -kx*imag + i*kx*real
        real = u_hat[i][0]
        imag = u_hat[i][1]
        k = kx[i]

        dudx_hat[i][0] = -k * imag  # Real part
        dudx_hat[i][1] = k * real   # Imag part
```

### Higher derivatives
∂²u/∂x² ↔ -kx² * û(k)

```python
@ti.kernel
def spectral_laplacian_2d():
    """Compute ∇²u in Fourier space: multiply by -(kx² + ky²)"""
    for i, j in ti.ndrange(N, N):
        k_sq = kx[i]**2 + ky[j]**2
        laplacian_hat[i, j][0] = -k_sq * u_hat[i, j][0]  # Real
        laplacian_hat[i, j][1] = -k_sq * u_hat[i, j][1]  # Imag
```

---

## 4) Pseudo-spectral method workflow

### Typical timestep for nonlinear PDE (e.g., Navier-Stokes)

1. **Physical space:** Compute nonlinear terms (e.g., u·∇u)
2. **FFT forward:** Transform to Fourier space
3. **Fourier space:** Apply linear operators (diffusion, pressure projection)
4. **Spectral derivatives:** Compute spatial derivatives
5. **FFT inverse:** Transform back to physical space
6. **Time integration:** Update fields (RK, IMEX, etc.)

### Example: 2D Navier-Stokes (vorticity-streamfunction)

```python
# Pseudo-code structure (using CuPy for FFTs)
def navier_stokes_step(omega, dt, nu):
    """
    Vorticity formulation: ∂ω/∂t + u·∇ω = ν∇²ω
    Streamfunction: ∇²ψ = -ω
    Velocity: u = ∂ψ/∂y, v = -∂ψ/∂x
    """
    # 1. Solve for streamfunction: ψ̂ = ω̂ / k²
    omega_hat = cp.fft.fft2(omega)
    psi_hat = -omega_hat / (kx_grid**2 + ky_grid**2 + 1e-12)  # Avoid k=0

    # 2. Compute velocity: u = ∂ψ/∂y, v = -∂ψ/∂x
    u_hat = 1j * ky_grid * psi_hat
    v_hat = -1j * kx_grid * psi_hat
    u = cp.fft.ifft2(u_hat).real
    v = cp.fft.ifft2(v_hat).real

    # 3. Compute advection: u·∇ω in physical space
    domega_dx_hat = 1j * kx_grid * omega_hat
    domega_dy_hat = 1j * ky_grid * omega_hat
    domega_dx = cp.fft.ifft2(domega_dx_hat).real
    domega_dy = cp.fft.ifft2(domega_dy_hat).real
    advection = u * domega_dx + v * domega_dy

    # 4. Spectral diffusion: ν∇²ω
    advection_hat = cp.fft.fft2(advection)
    diffusion_hat = -nu * (kx_grid**2 + ky_grid**2) * omega_hat

    # 5. Time integration (explicit Euler)
    omega_hat_new = omega_hat + dt * (-advection_hat + diffusion_hat)
    omega[:] = cp.fft.ifft2(omega_hat_new).real

    return omega
```

---

## 5) Dealiasing (preventing aliasing errors in nonlinear terms)

### The problem
FFT assumes periodicity. Nonlinear products (e.g., u·∇u) create high-frequency components that alias back into resolved scales.

### Solution: 2/3 rule
Zero out the top 1/3 of wavenumbers after computing nonlinear terms:

```python
@ti.kernel
def dealias_2thirds(field_hat: ti.template(), N: ti.i32):
    """Zero out wavenumbers |k| > 2N/3"""
    cutoff = ti.i32(2 * N // 3)
    for i, j in field_hat:
        kx_abs = abs(i if i < N//2 else i - N)
        ky_abs = abs(j if j < N//2 else j - N)
        if kx_abs > cutoff or ky_abs > cutoff:
            field_hat[i, j][0] = 0.0  # Real
            field_hat[i, j][1] = 0.0  # Imag
```

**When to dealias:**
- After computing nonlinear terms in Fourier space
- Not needed for linear terms

### Alternative: Zero-padding
Pad domain to 3N/2, compute products, then truncate. More accurate but 2-3x more expensive.

---

## 6) Time integration with spectral methods

### Integrating Factor (IF) method
For diffusion term ν∇²u, use exact exponential integrator:
```
u(t + dt) = e^{ν∇²dt} u(t) + ∫₀^dt e^{ν∇²(dt-s)} N(u(s)) ds
```

In Fourier space:
```python
# Linear part: exact solution
linear_factor = cp.exp(-nu * k_sq * dt)
u_hat *= linear_factor

# Nonlinear part: RK time-stepping
# (See ETDRK schemes for better accuracy)
```

### IMEX schemes
- **Implicit:** Diffusion (stiff, high wavenumbers)
- **Explicit:** Advection (non-stiff)

Example (Crank-Nicolson + Adams-Bashforth):
```python
# Implicit diffusion: (1 + 0.5*ν*dt*∇²) u^{n+1} = (1 - 0.5*ν*dt*∇²) u^n + dt*N^n
# In Fourier space:
denominator = 1.0 + 0.5 * nu * dt * k_sq
numerator = (1.0 - 0.5 * nu * dt * k_sq) * u_hat + dt * nonlinear_hat
u_hat_new = numerator / denominator
```

---

## 7) Example: 2D turbulence simulation (complete)

```python
import taichi as ti
import cupy as cp
import numpy as np

ti.init(arch=ti.cuda)

N = 512
L = 2 * np.pi
dx = L / N
dt = 0.001
nu = 1e-4

# Wavenumber grids
kx = cp.fft.fftfreq(N, d=dx/(2*np.pi))
ky = cp.fft.fftfreq(N, d=dx/(2*np.pi))
kx_grid, ky_grid = cp.meshgrid(kx, ky, indexing='ij')
k_sq = kx_grid**2 + ky_grid**2
k_sq[0, 0] = 1.0  # Avoid division by zero

# Initial condition: random vorticity
omega = ti.field(ti.f32, shape=(N, N))
omega_np = np.random.randn(N, N).astype(np.float32)
omega.from_numpy(omega_np)

# Main loop
for step in range(1000):
    # Transfer to CuPy
    omega_cp = cp.asarray(omega.to_numpy())
    omega_hat = cp.fft.fft2(omega_cp)

    # Solve for streamfunction
    psi_hat = -omega_hat / k_sq

    # Compute velocity
    u_hat = 1j * ky_grid * psi_hat
    v_hat = -1j * kx_grid * psi_hat
    u = cp.fft.ifft2(u_hat).real
    v = cp.fft.ifft2(v_hat).real

    # Advection in physical space
    domega_dx = cp.fft.ifft2(1j * kx_grid * omega_hat).real
    domega_dy = cp.fft.ifft2(1j * ky_grid * omega_hat).real
    advection = u * domega_dx + v * domega_dy

    # Update in Fourier space
    advection_hat = cp.fft.fft2(advection)
    rhs_hat = -advection_hat - nu * k_sq * omega_hat
    omega_hat_new = omega_hat + dt * rhs_hat

    # Dealias (optional but recommended)
    cutoff = 2 * N // 3
    mask = (cp.abs(kx_grid) > cutoff) | (cp.abs(ky_grid) > cutoff)
    omega_hat_new[mask] = 0

    # Back to Taichi
    omega_new = cp.fft.ifft2(omega_hat_new).real
    omega.from_numpy(cp.asnumpy(omega_new))

    if step % 100 == 0:
        print(f"Step {step}, Energy: {cp.sum(omega_cp**2).get():.3e}")
```

---

## 8) GPU performance considerations

### Memory transfers
- **Minimize host-device copies:** Keep data on GPU as long as possible
- Use `cp.asarray()` with Taichi fields to avoid unnecessary copies
- Consider persistent GPU allocations for intermediate arrays

### FFT plan reuse
- Create FFT plans once outside main loop
- Reuse plans for all transforms of the same size

### Kernel fusion
- Combine spectral derivative computation with other operations in single Taichi kernels
- Reduce temporary allocations

### Precision
- `float32` is sufficient for most spectral methods (and 2x faster than float64 on many GPUs)
- Use `float64` if you need >6 digits of accuracy or have ill-conditioned problems

---

## 9) Common pitfalls (gotchas)

### Wrong wavenumber convention
❌ **WRONG:** Using `[0, 1, 2, ..., N-1]` for wavenumbers
✓ **CORRECT:** Use FFTW convention `[0, 1, ..., N/2-1, -N/2, ..., -1]`

### Forgetting normalization
FFT libraries differ in normalization. Check docs and be consistent:
- NumPy/CuPy: Forward FFT has no normalization, inverse has 1/N
- FFTW: Forward 1/N, inverse none (or both √N depending on plan)

### Dealiasing nonlinear terms
Always dealias after computing products in physical space, before using in spectral updates.

### k = 0 mode
The mean (DC component) often needs special handling:
```python
# Remove mean (for incompressible flows)
omega_hat[0, 0] = 0
```

---

## 10) Validation (spectral method sanity checks)

Minimum tests:
- **Spectral accuracy:** For smooth solutions, error should decay exponentially with N
- **Energy conservation:** For inviscid (ν=0) flows, total energy should be conserved
- **Symmetry:** Symmetric initial conditions should remain symmetric
- **Derivative accuracy:** Test ∂u/∂x against finite differences for known functions

### Example: Test spectral derivative
```python
def test_spectral_derivative():
    """Verify spectral derivative against analytical result"""
    N = 128
    L = 2 * np.pi
    x = np.linspace(0, L, N, endpoint=False)

    # Test function: u = sin(2πx/L)
    u = np.sin(2 * np.pi * x / L)
    dudx_exact = (2 * np.pi / L) * np.cos(2 * np.pi * x / L)

    # Spectral derivative
    u_hat = np.fft.fft(u)
    kx = np.fft.fftfreq(N, d=L/N) * 2 * np.pi
    dudx_hat = 1j * kx * u_hat
    dudx_spectral = np.fft.ifft(dudx_hat).real

    error = np.max(np.abs(dudx_spectral - dudx_exact))
    assert error < 1e-10, f"Error too large: {error}"
```

### Convergence test (spectral vs FD)
For smooth solutions, spectral methods should achieve machine precision, while FD methods converge at polynomial rate (O(dx²), O(dx⁴), etc.).

---

## 11) References and further reading

- `references/interop.md` - Taichi-CuPy-CUDA interoperability patterns
- `references/kernel-patterns.md` - Complex arithmetic in Taichi
- `references/numerical-safeguards.md` - Stability and validation
- `domains/fd.md` - Comparison with finite difference methods
- `domains/linear-solvers.md` - Iterative solvers for implicit steps

For theoretical background:
- Boyd, "Chebyshev and Fourier Spectral Methods"
- Canuto et al., "Spectral Methods: Fundamentals in Single Domains"
- Durran, "Numerical Methods for Fluid Dynamics" (Chapter on spectral methods)
- Trefethen, "Spectral Methods in MATLAB"

### Online resources
- CuPy FFT documentation: https://docs.cupy.dev/en/stable/reference/fft.html
- cuFFT library guide: https://docs.nvidia.com/cuda/cufft/
- FFTW manual: http://www.fftw.org/fftw3_doc/
