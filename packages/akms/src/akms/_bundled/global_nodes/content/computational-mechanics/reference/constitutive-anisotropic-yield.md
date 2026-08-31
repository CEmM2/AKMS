# Anisotropic Yield Criteria

## Overview

Anisotropic yield functions account for directional dependence of plastic flow in materials with preferred orientations (rolling, extrusion, forging textures).

**Key applications**:
- Sheet metal forming (aluminum, steel)
- Textured metals (crystallographic anisotropy)
- Composite materials
- Additive manufacturing (layer-wise anisotropy)

---

## 1. Barlat 2004-18p

High-fidelity yield surface for textured metals, especially aluminum alloys.

### Formulation

Two linear transformations of the stress deviator:

$$\mathbf{s}' = \mathbf{L}'\mathbf{s}, \quad \mathbf{s}'' = \mathbf{L}''\mathbf{s}$$

where:
- $\mathbf{L}'$, $\mathbf{L}''$ are 6×6 anisotropy matrices
- $\mathbf{s}$ is the stress deviator in Voigt notation: $[\mathbf{s}] = [s_{11}, s_{22}, s_{33}, s_{23}, s_{13}, s_{12}]^T$
- 18 independent parameters total (9 per matrix after symmetry)

### Yield Function

$$\Phi = \left[\frac{1}{4}\sum_{i=1}^{3}\sum_{j=1}^{3}|\lambda'_i - \lambda''_j|^a\right]^{1/a} - \sigma_y = 0$$

where:
- $\lambda'_i$: eigenvalues of $\mathbf{s}'$ (3 principal values)
- $\lambda''_j$: eigenvalues of $\mathbf{s}''$ (3 principal values)
- $a$: yield exponent (8 for FCC metals, 6 for BCC metals)
- $\sigma_y$: current yield stress (may depend on hardening)

**Physical interpretation**: The yield surface is determined by differences between two sets of principal stresses obtained from different linear transformations of the deviator.

### Eigenvalue Computation

For GPU/analytical computation, use **Cardano's formula** (cubic characteristic equation) rather than iterative eigensolvers.

**Invariants of symmetric 3×3 matrix** $\mathbf{A}$:
```
I₁ = tr(A) = a₁₁ + a₂₂ + a₃₃
I₂ = ½[(tr A)² - tr(A²)] = a₁₁a₂₂ + a₂₂a₃₃ + a₃₃a₁₁ - a₁₂² - a₂₃² - a₁₃²
I₃ = det(A)

Characteristic equation: λ³ - I₁λ² + I₂λ - I₃ = 0

Cardano's method (substitution λ = μ + I₁/3):
  p = I₂ - I₁²/3
  q = I₃ - I₁I₂/3 + 2I₁³/27

For 3 real roots (typical for stress deviators):
  r = √(-p/3)
  φ = (1/3)arccos(-q/(2r³))

Eigenvalues:
  λ₁ = 2r·cos(φ) + I₁/3
  λ₂ = 2r·cos(φ + 2π/3) + I₁/3
  λ₃ = 2r·cos(φ + 4π/3) + I₁/3
```

**Numerical stability notes**:
- Clamp arccos argument to [-1, 1]
- For nearly diagonal matrices (|p| < ε), use diagonal entries directly
- Sort eigenvalues for consistent ordering

### Transformation Matrices

$\mathbf{L}'$ and $\mathbf{L}''$ contain anisotropy coefficients derived from experimental data:

**Calibration tests**:
- Uniaxial tension/compression at various angles (0°, 45°, 90° minimum)
- Biaxial tests (bulge test, plane strain tension)
- r-values (Lankford coefficients) measuring width/thickness strain ratio

**Isotropic case** (von Mises recovery):
```
L' = L'' = deviatoric projection operator
       ⎡ 2/3  -1/3  -1/3   0   0   0 ⎤
       ⎢-1/3   2/3  -1/3   0   0   0 ⎥
       ⎢-1/3  -1/3   2/3   0   0   0 ⎥
L_iso =⎢  0     0     0    1   0   0 ⎥
       ⎢  0     0     0    0   1   0 ⎥
       ⎣  0     0     0    0   0   1 ⎦
```

**Example anisotropic matrices** (2008-T4 aluminum, illustrative):
```
        ⎡ 0.069   0.936  -0.079   0   0   0 ⎤
        ⎢ 0.079   0.931  -0.082   0   0   0 ⎥
        ⎢ 0.005  -0.010   1.005   0   0   0 ⎥
L'   =  ⎢   0       0       0     1   0   0 ⎥
        ⎢   0       0       0     0   1   0 ⎥
        ⎣   0       0       0     0   0   1 ⎦

        ⎡ 0.981   0.028   0.029   0   0   0 ⎤
        ⎢ 0.030   0.992   0.051   0   0   0 ⎥
        ⎢-0.008  -0.020   0.972   0   0   0 ⎥
L''  =  ⎢   0       0       0     1   0   0 ⎥
        ⎢   0       0       0     0   1   0 ⎥
        ⎣   0       0       0     0   0   1 ⎦
```

### Flow Direction

**Plastic flow direction** (assuming associative flow):

$$\mathbf{N} = \frac{\partial\Phi}{\partial\boldsymbol{\sigma}}$$

**Implementation options**:
1. **Automatic differentiation**: Let AD framework compute gradient (easiest, most robust)
2. **Manual derivative**: Chain rule through eigenvalues
   - Requires eigenvector computation
   - More complex but potentially faster

**Note**: The derivative involves:
- $\partial\lambda_i/\partial\mathbf{s}$ (eigenvector outer products)
- Chain rule through both transformation matrices

### Voigt Convention Notes

**Critical**: Ensure consistent Voigt stress convention across code:

**Tensor shear stress** $\tau_{12}$:
```
σ_voigt[5] = τ₁₂  (tensor component)
```

**Engineering shear stress** $2τ_{12}$:
```
σ_voigt[5] = 2τ₁₂  (engineering convention)
```

Most finite element codes use **tensor convention**. Check transformation matrices accordingly.

---

## 2. Hill's Anisotropic Yield (Simpler Alternative)

For less severe anisotropy, Hill's quadratic criterion is simpler:

$$f = F(\sigma_{22} - \sigma_{33})^2 + G(\sigma_{33} - \sigma_{11})^2 + H(\sigma_{11} - \sigma_{22})^2 + 2L\tau_{23}^2 + 2M\tau_{13}^2 + 2N\tau_{12}^2 - \sigma_y^2 = 0$$

**Advantages**:
- Only 6 parameters (F, G, H, L, M, N)
- Quadratic → closed-form flow direction
- No eigenvalue computation needed

**Limitations**:
- Less flexible for complex anisotropy
- Cannot capture yield asymmetry (tension/compression difference)

---

## 3. Implementation Considerations

### Return Mapping with Anisotropic Yield

**Trial state**:
$$\boldsymbol{\sigma}^{trial} = \boldsymbol{\sigma}_n + \mathbb{C}^e : \Delta\boldsymbol{\varepsilon}$$

**Check yield**:
$$f^{trial} = \Phi(\boldsymbol{\sigma}^{trial}) - \sigma_y(\bar{\varepsilon}^p_n)$$

**If** $f^{trial} > 0$: Plastic corrector (local Newton iteration)

$$\boldsymbol{\sigma}_{n+1} = \boldsymbol{\sigma}^{trial} - \Delta\lambda \mathbb{C}^e : \mathbf{N}$$

where $\mathbf{N} = \partial\Phi/\partial\boldsymbol{\sigma}$ (flow direction).

**Solve for** $\Delta\lambda$ such that $\Phi(\boldsymbol{\sigma}_{n+1}) = \sigma_y(\bar{\varepsilon}^p_{n+1})$.

### Consistent Tangent

For Newton convergence at global level:

$$\mathbb{C}^{ep} = \frac{\partial\boldsymbol{\sigma}}{\partial\boldsymbol{\varepsilon}}$$

**Implicit differentiation** of plastic corrector equations yields:

$$\mathbb{C}^{ep} = \mathbb{C}^e - \frac{(\mathbb{C}^e:\mathbf{N})\otimes(\mathbf{N}:\mathbb{C}^e)}{\mathbf{N}:\mathbb{C}^e:\mathbf{N} + h}$$

where $h = \partial\sigma_y/\partial\bar{\varepsilon}^p$ (hardening modulus).

**Note**: For Barlat, $\mathbf{N}$ computation is expensive → consider caching or approximations.

### GPU/Parallel Considerations

- **Eigenvalue solver**: Analytical (Cardano) parallelizes well, iterative solvers do not
- **Flow direction**: If using autodiff, ensure compatibility with GPU kernels
- **Matrix transformations**: $\mathbf{L}'\mathbf{s}$ and $\mathbf{L}''\mathbf{s}$ are embarrassingly parallel

---

## 4. Verification Tests

### Isotropic Limit Check

Set $\mathbf{L}' = \mathbf{L}'' = \mathbf{L}_{iso}$ → should recover von Mises:

**Uniaxial tension** ($\sigma_{11} = \sigma_y$, others zero):
```
Expected: σ_eq ≈ σ_y  (yield function Φ = f ≈ 0)
```

**Pure shear** ($\tau_{12} = \sigma_y/\sqrt{3}$):
```
Expected: σ_eq ≈ σ_y  (yield function Φ = f ≈ 0)
```

### Directional Yield Strength

For calibrated anisotropic matrices:

**Test uniaxial stress at angles** θ = 0°, 45°, 90°:

Apply a uniaxial stress of magnitude $\sigma_0$ at angle $\theta$ to the 1-axis in the 1-2 plane. The stress components in Voigt notation are:
```
σ(θ) = [σ₀·cos²θ, σ₀·sin²θ, 0, 0, 0, σ₀·sinθ·cosθ]
       (σ₁₁,     σ₂₂,     σ₃₃, σ₂₃, σ₁₃, σ₁₂)

Compute: σ_eq(θ) / σ_y  (anisotropy ratio)
```

Should match experimental r-values within calibration tolerance.

---

## See Also

- `constitutive-viscoplastic-thermo.md` - Rate-dependent plasticity frameworks
- `objective-rates-integration.md` - Large deformation considerations
- `templates/barlat_2004_numpy.py` - NumPy reference implementation
- `templates/barlat_2004_taichi.py` - GPU-optimized Taichi implementation
- `verification-benchmarks.md` - Barlat biaxial benchmark test
