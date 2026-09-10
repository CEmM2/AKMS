# Phase-field Fracture (Brittle)

## Overview

Phase-field methods regularize sharp crack discontinuities into smooth degradation zones, enabling crack nucleation, propagation, and branching without explicit crack tracking.

**Core concept**: Replace sharp crack surface $\Gamma$ with diffuse field $\phi(\mathbf{x})$:
- $\phi = 0$: intact material
- $\phi = 1$: fully broken
- $0 < \phi < 1$: transition zone (crack bandwidth ~ $2\ell$)

---

## 1. Energy Functional

Total energy combines elastic strain energy and fracture dissipation:

$$\mathcal{E}(\mathbf{u}, \phi) = \int_\Omega \psi_e(\boldsymbol{\varepsilon}, \phi)\,dV + \int_\Omega G_c\gamma(\phi, \nabla\phi)\,dV$$

where:
- $\mathbf{u}$: displacement field
- $\phi$: phase-field (damage parameter)
- $\psi_e$: degraded elastic strain energy density
- $G_c$: critical energy release rate (fracture toughness) [J/m²]
- $\gamma$: crack surface density function

### AT-2 Formulation (Miehe)

**Crack surface density** (Ambrosio-Tortorelli regularization):

$$\gamma(\phi, \nabla\phi) = \frac{1}{2\ell}\phi^2 + \frac{\ell}{2}|\nabla\phi|^2$$

**Length scale** $\ell$ controls:
- Crack bandwidth: width ≈ $2\ell$
- Mesh size requirement: $h < \ell/2$ for proper resolution
- Smaller $\ell$ → sharper crack, finer mesh needed

**Sharp crack limit**: As $\ell \to 0$, $\gamma \to \Gamma$ (crack surface)

---

## 2. Spectral Energy Split (Miehe)

**Purpose**: Prevent cracking under compression (physically incorrect for brittle materials).

### Principal Strain Decomposition

Decompose strain tensor into principal components:

$$\boldsymbol{\varepsilon} = \sum_{a=1}^{3}\varepsilon_a\mathbf{n}_a\otimes\mathbf{n}_a$$

where $\varepsilon_a$ are principal strains and $\mathbf{n}_a$ are principal directions.

**Positive/negative parts**:

$$\boldsymbol{\varepsilon}^+ = \sum_{a=1}^{3}\langle\varepsilon_a\rangle_+\mathbf{n}_a\otimes\mathbf{n}_a, \quad \boldsymbol{\varepsilon}^- = \boldsymbol{\varepsilon} - \boldsymbol{\varepsilon}^+$$

where $\langle x \rangle_+ = \max(x, 0)$ (Macaulay bracket).

### Split Strain Energies

**Tensile part** (degraded by damage):

$$\psi^+ = \frac{\lambda}{2}\langle\text{tr}(\boldsymbol{\varepsilon})\rangle_+^2 + \mu\,\text{tr}\left((\boldsymbol{\varepsilon}^+)^2\right)$$

**Compressive part** (not degraded):

$$\psi^- = \frac{\lambda}{2}\langle\text{tr}(\boldsymbol{\varepsilon})\rangle_-^2 + \mu\,\text{tr}\left((\boldsymbol{\varepsilon}^-)^2\right)$$

where:
- $\lambda, \mu$: Lamé parameters
- $\langle\text{tr}(\boldsymbol{\varepsilon})\rangle_+ = \max(\text{tr}(\boldsymbol{\varepsilon}), 0)$
- $\text{tr}((\boldsymbol{\varepsilon}^{\pm})^2) = \sum_a (\varepsilon_a^{\pm})^2$

---

## 3. Degradation Function

Stiffness degrades smoothly from intact to broken:

$$g(\phi) = (1-\phi)^2 + k$$

where:
- $k \sim 10^{-6}$ to $10^{-8}$: residual stiffness (prevents singularity)
- $g(0) = 1$: intact material
- $g(1) = k$: broken material (nearly zero stiffness)

**Critical**: $k$ should be small enough not to affect fracture energy but large enough to prevent numerical issues.

---

## 4. Degraded Stress

Only tensile energy is degraded by damage:

$$\boldsymbol{\sigma} = g(\phi)\frac{\partial\psi^+}{\partial\boldsymbol{\varepsilon}} + \frac{\partial\psi^-}{\partial\boldsymbol{\varepsilon}}$$

**Explicit form**:

$$\boldsymbol{\sigma} = g(\phi)\left[\lambda\langle\text{tr}(\boldsymbol{\varepsilon})\rangle_+\mathbf{I} + 2\mu\boldsymbol{\varepsilon}^+\right] + \lambda\langle\text{tr}(\boldsymbol{\varepsilon})\rangle_-\mathbf{I} + 2\mu\boldsymbol{\varepsilon}^-$$

**Physical interpretation**:
- Compression ($\text{tr}(\boldsymbol{\varepsilon}) < 0$): stress unaffected by damage
- Tension ($\text{tr}(\boldsymbol{\varepsilon}) > 0$): stress reduced by $g(\phi)$

---

## 5. Phase-Field Evolution

**Euler-Lagrange equation** (Allen-Cahn type):

$$g'(\phi)\mathcal{H} + G_c\left(\frac{\phi}{\ell} - \ell\nabla^2\phi\right) = 0$$

where:
- $g'(\phi) = -2(1-\phi)$: derivative of degradation function
- $\mathcal{H}$: history variable (see below)

**Weak form** (for FEM implementation):

$$\int_\Omega \left[-2(1-\phi)\mathcal{H}\delta\phi + G_c\left(\frac{\phi\delta\phi}{\ell} + \ell\nabla\phi\cdot\nabla\delta\phi\right)\right]dV = 0$$

---

## 6. Irreversibility via History Field

**History variable** enforces crack irreversibility (no healing):

$$\mathcal{H}(t) = \max_{\tau \in [0,t]}\psi^+(\tau)$$

**Implementation**:
```python
# At each integration point
H_new = max(psi_plus_current, H_old)
# Use H_new in phase-field equation
```

**Physical meaning**: Crack can only grow or remain stationary, never shrink.

### Alternative: Direct Constraint

Instead of history field, enforce pointwise:

$$\phi_{n+1} = \max(\phi_{n+1}^{solved}, \phi_n)$$

after solving phase-field equation. Simpler but may affect energy consistency.

---

## 7. Solution Strategy (Staggered)

**Default approach**: Alternating minimization (staggered scheme)

### Algorithm

```
For each time step n → n+1:
  1) Fix φ_n, solve mechanics for u_{n+1}:
     - Compute ε from u
     - Split: ε^+, ε^-
     - Compute degraded stress: σ = g(φ_n) ∂ψ^+/∂ε + ∂ψ^-/∂ε
     - Solve equilibrium: div(σ) = 0

  2) Fix u_{n+1}, solve phase-field for φ_{n+1}:
     - Update history: H = max(ψ^+, H_old)
     - Solve: g'(φ)H + G_c(φ/ℓ - ℓ∇²φ) = 0
     - (Linear or quadratic equation)

  3) Enforce irreversibility:
     φ_{n+1} = max(φ_{n+1}, φ_n)

  4) Check convergence:
     If ||φ_{n+1} - φ_n|| < tol: accept step
     Else: iterate steps 1-3 (staggered loop)
```

**Convergence criterion**: Typically 2-5 staggered iterations per load step.

---

## 8. Implementation Checks

### Verification Tests

1. **No compression cracking**:
   - Apply hydrostatic compression: $\boldsymbol{\sigma} = -p\mathbf{I}$
   - Verify $\phi$ remains zero (no damage growth)

2. **Crack bandwidth**:
   - Measure transition zone width in converged solution
   - Should be approximately $2\ell$

3. **Energy balance**:
   - Elastic energy release ≈ Fracture dissipation
   - $\Delta\psi_e \approx G_c \times \text{(crack area)}$

4. **Mesh convergence**:
   - Refine mesh with $h < \ell/2$
   - Crack path and load-displacement curve should converge

### Numerical Parameters

| Parameter | Typical Value | Notes |
|-----------|---------------|-------|
| $k$ (residual) | $10^{-6}$ to $10^{-8}$ | Too large → wrong fracture energy |
| $\ell$ (length scale) | 0.01 to 0.1 mm | Problem-dependent |
| $h$ (mesh size) | $< \ell/2$ | Finer for sharp cracks |
| Staggered tolerance | $10^{-4}$ | On $\|\phi_{k+1} - \phi_k\|$ |

### Common Pitfalls

- **Mesh too coarse**: $h > \ell$ → crack width wrong, energy incorrect
- **$k$ too large**: Residual stiffness affects fracture toughness
- **No history field**: Cracks can heal spuriously during unloading
- **Compression cracking**: Forgot energy split → non-physical damage under compression

---

## 9. Extensions

### Plasticity Coupling

For ductile fracture, combine with plastic dissipation:

$$\psi_{total} = g(\phi)\psi_e^+ + \psi_e^- + \psi_p$$

where $\psi_p$ is plastic dissipation (see `ductile-fracture-gtn-phasefield.md`).

### Dynamics

Add inertia and rate effects:

$$\rho\ddot{\mathbf{u}} = \nabla\cdot\boldsymbol{\sigma}, \quad \eta\dot{\phi} + g'(\phi)\mathcal{H} + G_c(\phi/\ell - \ell\nabla^2\phi) = 0$$

where $\eta$ is phase-field viscosity (regularization).

---

## See Also

- `ductile-fracture-gtn-phasefield.md` - Coupling with plasticity
- `solver-architecture-matrixfree.md` - Matrix-free staggered solvers
- `templates/miehe_spectral_split.py` - Spectral split implementation
- `templates/phasefield_staggered_solver.py` - Staggered solution template
- `verification-benchmarks.md` - Sneddon crack benchmark
