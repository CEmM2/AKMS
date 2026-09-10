# FFT-Galerkin Micromechanics (Periodic RVEs)

## Overview

FFT-based solvers for periodic heterogeneous materials (representative volume elements - RVEs). Faster than FEM for regular grids due to FFT efficiency ($O(N\log N)$ vs $O(N^{3/2})$ for sparse FEM).

**Key applications**:
- Computational homogenization of composites
- Polycrystal plasticity
- Microstructure-sensitive fracture
- Digital materials design

---

## 1. Problem Statement

Find strain field $\boldsymbol{\varepsilon}(\mathbf{x})$ in periodic RVE $\Omega$ satisfying:

$$\nabla \cdot \boldsymbol{\sigma} = 0 \quad \text{in } \Omega$$
$$\boldsymbol{\sigma}(\mathbf{x}) = \mathbb{C}(\mathbf{x}) : \boldsymbol{\varepsilon}(\mathbf{x})$$
$$\langle\boldsymbol{\varepsilon}\rangle = \bar{\boldsymbol{\varepsilon}} \quad \text{(prescribed macroscopic strain)}$$

with periodic boundary conditions on $\partial\Omega$.

**Boundary condition options**:
- **Strain control**: Prescribe $\bar{\boldsymbol{\varepsilon}}$, compute $\bar{\boldsymbol{\sigma}}$
- **Stress control**: Prescribe $\bar{\boldsymbol{\sigma}}$, compute $\bar{\boldsymbol{\varepsilon}}$
- **Mixed control**: Some components prescribed, others free

---

## 2. Lippmann-Schwinger Equation

### Derivation

Introduce reference medium $\mathbb{C}^0$ (homogeneous, typically isotropic) and polarization stress:

$$\boldsymbol{\tau}(\mathbf{x}) = (\mathbb{C}(\mathbf{x}) - \mathbb{C}^0) : \boldsymbol{\varepsilon}(\mathbf{x})$$

Equilibrium becomes:
$$\nabla \cdot (\mathbb{C}^0 : \boldsymbol{\varepsilon} + \boldsymbol{\tau}) = 0$$

Using Green's function of reference medium:

$$\boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}} - (\boldsymbol{\Gamma}^0 * \boldsymbol{\tau})(\mathbf{x})$$

This is the **Lippmann-Schwinger equation**—implicit because $\boldsymbol{\tau}$ depends on $\boldsymbol{\varepsilon}$.

### Fourier Space Form

Convolution becomes pointwise multiplication:

$$\hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) = \bar{\boldsymbol{\varepsilon}}\delta(\boldsymbol{\xi}) - \hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) : \hat{\boldsymbol{\tau}}(\boldsymbol{\xi})$$

For $\boldsymbol{\xi} \neq 0$:
$$\hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) = -\hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) : \hat{\boldsymbol{\tau}}(\boldsymbol{\xi})$$

For $\boldsymbol{\xi} = 0$ (DC component):
$$\hat{\boldsymbol{\varepsilon}}(0) = \bar{\boldsymbol{\varepsilon}} \quad \text{(macroscopic average)}$$

**Critical**: Zero frequency ($\boldsymbol{\xi} = 0$) must be handled separately to enforce macroscopic control.

---

## 3. Green's Operator

### Definition

Fourth-order tensor $\boldsymbol{\Gamma}^0$ derived from Green's function:

$$\Gamma^0_{ijkl}(\mathbf{x}) = -G^0_{ki,jl}(\mathbf{x})$$

### Fourier Space (Isotropic Reference)

$$\hat{\Gamma}^0_{ijkl}(\boldsymbol{\xi}) = \frac{1}{4\mu^0|\boldsymbol{\xi}|^2}\left(\delta_{ki}\xi_l\xi_j + \delta_{li}\xi_k\xi_j + \delta_{kj}\xi_l\xi_i + \delta_{lj}\xi_k\xi_i\right) - \frac{\lambda^0+\mu^0}{\mu^0(\lambda^0+2\mu^0)}\frac{\xi_i\xi_j\xi_k\xi_l}{|\boldsymbol{\xi}|^4}$$

where $\lambda^0$, $\mu^0$ are Lamé constants of reference medium.

### Acoustic Tensor Form (More General)

Define the **acoustic tensor** (second-order):

$$K^0_{im}(\boldsymbol{\xi}) = C^0_{ijkl}\xi_j\xi_l$$

Then its inverse:

$$\hat{G}^0_{km}(\boldsymbol{\xi}) = \left[K^0\right]^{-1}_{km}(\boldsymbol{\xi})$$

The **Green's operator** (fourth-order) is constructed as:

$$\hat{\Gamma}^0_{ijkl}(\boldsymbol{\xi}) = \text{Sym}_{(i,j),(k,l)}\left[\xi_k \hat{G}^0_{il}(\boldsymbol{\xi}) \xi_j\right]$$

where $\text{Sym}_{(i,j),(k,l)}$ denotes symmetrization over index pairs $(i,j)$ and $(k,l)$:

$$\text{Sym}_{(i,j),(k,l)}[T_{ijkl}] = \frac{1}{4}(T_{ijkl} + T_{jikl} + T_{ijlk} + T_{jilk})$$

**Note**: This form works for anisotropic reference media.

---

## 4. Iterative Solvers

### 4.1 Basic Scheme (Moulinec-Suquet)

Fixed-point iteration:

```
Initialize: ε⁰(x) = ε̄

For k = 0, 1, 2, ... until convergence:

    1. Constitutive (real space):
       σᵏ(x) = C(x) : εᵏ(x)
       τᵏ(x) = σᵏ(x) - C⁰ : εᵏ(x)

    2. FFT:
       τ̂ᵏ(ξ) = FFT(τᵏ(x))

    3. Update (Fourier space):
       ε̂ᵏ⁺¹(ξ) = -Γ̂⁰(ξ) : τ̂ᵏ(ξ)  for ξ ≠ 0
       ε̂ᵏ⁺¹(0) = ε̄               (enforce macro)

    4. IFFT:
       εᵏ⁺¹(x) = IFFT(ε̂ᵏ⁺¹(ξ))

    5. Check convergence:
       ||div(σᵏ)|| / ||⟨σᵏ⟩|| < tol
```

**Convergence criterion** (equilibrium in Fourier space):

$$\frac{\sqrt{\sum_{\boldsymbol{\xi}\neq 0}|\boldsymbol{\xi}\cdot\hat{\boldsymbol{\sigma}}|^2}}{|\hat{\boldsymbol{\sigma}}(0)|} < tol$$

Typical tolerance: $tol = 10^{-6}$ to $10^{-8}$.

**Pros**: Simple, low memory
**Cons**: Slow for high contrast (>100:1) or strong nonlinearity, can require >1000 iterations

### 4.2 Reference Medium Selection

**Critical** for convergence. Common choices:

**Arithmetic mean** (good for moderate contrast):
$$\lambda^0 = \frac{1}{2}(\lambda_{min} + \lambda_{max}), \quad \mu^0 = \frac{1}{2}(\mu_{min} + \mu_{max})$$

**Geometric mean** (better for high contrast):
$$\mu^0 = \sqrt{\mu_{min}\mu_{max}}$$

**Adaptive**: Recompute $\mathbb{C}^0$ every few iterations based on current stress state.

### 4.3 Accelerated Polarization Schemes

**Augmented Lagrangian** (Michel et al.):

```
Initialize: λ⁰ = 0

For k = 0, 1, 2, ... until convergence:
    εᵏ⁺¹ = ε̄ - Γ̂⁰ : λᵏ
    eᵏ⁺¹ = (C + C⁰)⁻¹ : (C⁰ : εᵏ⁺¹ + λᵏ)
    λᵏ⁺¹ = λᵏ + C⁰ : (εᵏ⁺¹ - eᵏ⁺¹)
```

**Pros**: Converges for infinite contrast (voids, rigid inclusions)
**Typical iterations**: ~100 regardless of contrast

### 4.4 Newton-Krylov / CG (Recommended)

Treat Lippmann-Schwinger as nonlinear system:

$$\mathcal{R}(\boldsymbol{\varepsilon}) = \boldsymbol{\varepsilon} + \mathcal{F}^{-1}\left[\hat{\boldsymbol{\Gamma}}^0 : \mathcal{F}[(\mathbb{C}-\mathbb{C}^0):\boldsymbol{\varepsilon}]\right] - \bar{\boldsymbol{\varepsilon}} = 0$$

**Newton iteration**:
$$\boldsymbol{\varepsilon}^{k+1} = \boldsymbol{\varepsilon}^k - \left[\frac{\partial\mathcal{R}}{\partial\boldsymbol{\varepsilon}}\right]^{-1}\mathcal{R}(\boldsymbol{\varepsilon}^k)$$

**Tangent operator**:
$$\frac{\partial\mathcal{R}}{\partial\boldsymbol{\varepsilon}}[\delta\boldsymbol{\varepsilon}] = \delta\boldsymbol{\varepsilon} + \mathcal{F}^{-1}[\hat{\boldsymbol{\Gamma}}^0 : \mathcal{F}[(\mathbb{C}^{tan} - \mathbb{C}^0):\delta\boldsymbol{\varepsilon}]]$$

where $\mathbb{C}^{tan} = \partial\boldsymbol{\sigma}/\partial\boldsymbol{\varepsilon}$ is the algorithmic tangent from constitutive update.

**Solve inner system** with Krylov method (CG or GMRES):
- Matrix-free: only need Jacobian-vector products (JVPs)
- Typical iterations: 10-20 Newton steps × 5-10 CG iterations

**Pros**: Fast convergence for any contrast, handles strong nonlinearity
**Cons**: Requires consistent tangent from constitutive model

---

## 5. Nonlinear Constitutive Laws

### Time-Stepping for Plasticity

March through load history (pseudo-time):

```
For load step n → n+1:
    ε̄ₙ₊₁ = prescribed macroscopic strain

    Solve: ε(x) such that div(σ(ε, history)) = 0

    At each voxel:
        - Local constitutive update (return mapping)
        - Update internal variables (Fᵖ, α, φ, etc.)
        - Compute tangent ∂σ/∂ε
```

### Local State Update

At each grid point (voxel), store:
- **Internal variables**: $\mathbf{F}^p$, $\bar{\varepsilon}^p$, $\phi$ (damage), hardening, etc.
- **History**: for hysteretic/rate-dependent models

**Implicit integration** (e.g., radial return mapping):
```
Given: ε_new, state_old
Return: σ_new, state_new, C_tan
```

**Critical**: Return consistent tangent $\mathbb{C}^{tan}$ for Newton convergence.

---

## 6. FFT-Based Phase-Field Fracture

### Staggered Approach

Alternate between mechanical and phase-field sub-problems:

```
For each load step:
    Repeat until convergence:
        1. Fix φ, solve mechanics for ε:
           div(g(φ)·σ⁺ + σ⁻) = 0  (FFT solver)

        2. Fix ε, solve phase-field for φ:
           -2(1-φ)H + Gc(φ/ℓ - ℓ∇²φ) = 0  (FFT solver)

        3. Enforce φ_new = max(φ_new, φ_old)
```

### Phase-Field in Fourier Space

Helmholtz-type equation:

$$\phi + \ell^2\nabla^2\phi = \ell\frac{g'(\phi)\mathcal{H}}{G_c}$$

In Fourier space:

$$\hat{\phi}(\boldsymbol{\xi}) = \frac{\hat{h}(\boldsymbol{\xi})}{1 + \ell^2|\boldsymbol{\xi}|^2}$$

where $h = \ell g'(\phi)\mathcal{H}/G_c$ (computed in real space, then FFT'd).

**Advantage**: No matrix assembly, direct solve in Fourier space.

---

## 7. Computational Homogenization

### Effective Properties

**Macroscopic stress**:
$$\bar{\boldsymbol{\sigma}} = \langle\boldsymbol{\sigma}\rangle = \frac{1}{|\Omega|}\int_\Omega\boldsymbol{\sigma}(\mathbf{x})\,dV$$

In discrete form (voxel grid):
$$\bar{\boldsymbol{\sigma}} = \frac{1}{N_{vox}}\sum_{i=1}^{N_{vox}}\boldsymbol{\sigma}_i$$

**Effective stiffness tensor**:
$$\bar{\mathbb{C}} = \frac{\partial\bar{\boldsymbol{\sigma}}}{\partial\bar{\boldsymbol{\varepsilon}}}$$

Compute by perturbing macroscopic strain in 6 independent directions (Voigt components).

### Hill-Mandel Condition

Energy consistency (automatically satisfied with periodic BCs):

$$\bar{\boldsymbol{\sigma}} : \bar{\boldsymbol{\varepsilon}} = \langle\boldsymbol{\sigma}:\boldsymbol{\varepsilon}\rangle$$

**Verification**: Check this equality numerically (should hold to machine precision).

---

## 8. Implementation Notes

### 8.1 DFT Conventions

**Be consistent** with FFT normalization:

**NumPy/SciPy convention**:
```text
fft:  F[k] = Σ_n f[n] exp(-2πi kn/N)
ifft: f[n] = (1/N) Σ_k F[k] exp(2πi kn/N)
```

Factor of $1/N$ on inverse FFT.

### 8.2 Frequency Grid

For $N$ grid points with spacing $h$:

$$\xi_k = \begin{cases}
k/(Nh) & k < N/2 \\
(k-N)/(Nh) & k \geq N/2
\end{cases}$$

**DC component**: $\xi = 0$ at index $k=0$
**Nyquist frequency**: $\xi_{max} = 1/(2h)$ at $k = N/2$

### 8.3 Zero Frequency Handling

$\boldsymbol{\xi} = 0$ requires special treatment:

- $\hat{\boldsymbol{\Gamma}}^0(0)$ is undefined → **set to zero**
- $\hat{\boldsymbol{\varepsilon}}(0) = \bar{\boldsymbol{\varepsilon}}$ enforces macroscopic strain control
- $\hat{\boldsymbol{\sigma}}(0) = \bar{\boldsymbol{\sigma}}$ (average stress, for verification)

**Never** apply Green's operator at $\xi = 0$.

### 8.4 Symmetry and Efficiency

For **real-valued fields**, exploit conjugate symmetry:

$$\hat{f}(-\boldsymbol{\xi}) = \hat{f}^*(\boldsymbol{\xi})$$

Use **`rfft`** (real FFT) to save ~50% storage and computation:
```python
import numpy as np
f_hat = np.fft.rfftn(f_real)  # returns (Nx, Ny, Nz//2+1) complex array
```

### 8.5 Gibbs Phenomena

Sharp interfaces (cracks, voids, grain boundaries) cause Fourier ringing.

**Mitigation strategies**:
- Use discrete derivatives (finite differences in real space) instead of $i\xi$ in Fourier
- Apply spectral filtering
- Use rotated stencils (e.g., Willot scheme)

### 8.6 Typical Grid Sizes

| Dimension | Typical Range | Memory (float64) |
|-----------|---------------|------------------|
| 2D | $256^2$ to $1024^2$ | 0.5 MB to 8 MB |
| 3D | $64^3$ to $256^3$ | 2 MB to 128 MB |

**GPU**: Can handle up to $512^3$ with modern cards (requires ~1 GB for strain field alone).

---

## 9. Performance Comparison

| Method | Contrast | Typical Iterations | Memory | When to Use |
|--------|----------|-------------------|--------|-------------|
| Basic (Moulinec-Suquet) | Low (<10:1) | 50-100 | Low | Simple problems, prototyping |
| Basic | High (>100:1) | >1000 (slow!) | Low | Not recommended |
| Augmented Lagrangian | Any | ~100 | Medium | High contrast, voids/rigid |
| Newton-CG | Any | 10-20 outer | Medium | Recommended for nonlinear |

**Recommendation**: Use Newton-Krylov for production work (plasticity, fracture, high contrast).

---

## 10. Verification Tests

### Patch Test (Homogeneous Material)

Set $\mathbb{C}(\mathbf{x}) = \mathbb{C}^0$ everywhere:

**Expected**: Uniform strain $\boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}}$, uniform stress $\boldsymbol{\sigma}(\mathbf{x}) = \mathbb{C}^0:\bar{\boldsymbol{\varepsilon}}$

**Check**: $\max_x |\boldsymbol{\varepsilon}(\mathbf{x}) - \bar{\boldsymbol{\varepsilon}}| < tol$

### Inclusion Benchmark

**Eshelby problem**: Spherical/ellipsoidal inclusion in infinite matrix

**Compare**: FFT solution vs analytical Eshelby tensor

**Convergence**: Refine grid, check convergence of stress concentration factor

### Equilibrium Verification

**Fourier-space check**:

$$\text{error}_{eq} = \frac{\sqrt{\sum_{\boldsymbol{\xi}\neq 0}|\boldsymbol{\xi}\cdot\hat{\boldsymbol{\sigma}}(\boldsymbol{\xi})|^2}}{|\hat{\boldsymbol{\sigma}}(0)|}$$

Should decrease to $< 10^{-6}$ for converged solution.

### Hill-Mandel Energy Check

$$\left|\bar{\boldsymbol{\sigma}}:\bar{\boldsymbol{\varepsilon}} - \langle\boldsymbol{\sigma}:\boldsymbol{\varepsilon}\rangle\right| < 10^{-12}$$

Should be satisfied to machine precision with periodic BCs.

---

## See Also

- `solver-architecture-matrixfree.md` - Matrix-free Newton-Krylov implementation
- `phase-field-fracture.md` - Phase-field theory and staggered solvers
- `templates/fft_lippmann_schwinger.py` - FFT solver implementation
- `templates/newton_krylov_matrixfree.py` - Newton-Krylov template
- `verification-benchmarks.md` - Periodic RVE benchmark tests
