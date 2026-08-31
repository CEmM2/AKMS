---
name: computational-mechanics
description: |
  Derives and implements nonlinear solid mechanics algorithms: tensor calculus, finite-strain kinematics
  (Total Lagrangian, convected coordinates), rate- and temperature-dependent plasticity, brittle/ductile
  fracture (phase-field, GTN), and FFT-Galerkin micromechanics. Use for FEM/FFT constitutive updates,
  objective stress integration, solver architecture, and verification.
---

# Computational Mechanics

Entry-point Skill for computational mechanics implementation work.

## Scope

Use this Skill when the task involves **math-to-code translation** for:

- Tensor algebra/calculus (push-forward/pull-back, curvilinear/convected bases)
- Large deformation kinematics (Total Lagrangian, large rotations, large strains)
- Rate- and temperature-dependent plasticity (Perzyna, Duvaut-Lions, implicit BE)
- Brittle/ductile fracture (phase-field, Gurson/GTN family, coupling strategies)
- FFT-Galerkin micromechanics (Lippmann-Schwinger, Newton-Krylov, high contrast)

**Taichi note:** if Taichi code is requested, consult the `taichi-gpu-sim` Skill for Taichi-specific best practices and performance rules. This Skill focuses on the *mechanics*.

## Default standards

1. **State the configuration and stress measure** (e.g., TL with $S$ and $E$, or spatial with Cauchy $\sigma$ and $D$).
2. **Objectivity is non-negotiable**: use a corotational/objective update if integrating rates in the spatial frame.
3. **Finite strain plasticity** defaults to multiplicative split $F = F^e F^p$ unless small-strain is explicitly requested.
4. **Rate dependence** defaults to implicit backward Euler for stability.
5. **Phase-field fracture** defaults to staggered alternate minimization (u/phi) with a tension/compression energy split.
6. Prefer **matrix-free operators** (directional derivatives / JVPs) over assembled global tangents when scale/performance matters.

## Quick Reference

### Stress Measures
| Name | Symbol | Configuration | Conjugate Strain |
|------|--------|---------------|------------------|
| Cauchy | $\boldsymbol{\sigma}$ | Spatial | Rate of deformation $\mathbf{d}$ |
| 1st Piola-Kirchhoff | $\mathbf{P}$ | Two-point | $\dot{\mathbf{F}}$ |
| 2nd Piola-Kirchhoff | $\mathbf{S}$ | Reference | Green-Lagrange $\mathbf{E}$ |
| Kirchhoff | $\boldsymbol{\tau} = J\boldsymbol{\sigma}$ | Spatial | $\mathbf{d}$ |
| Mandel | $\mathbf{M} = \mathbf{C}^e\mathbf{S}$ | Intermediate | $\mathbf{L}^p$ |

### Key Transformations
```
Push-forward:   τ = F S F^T        (S → τ)
Pull-back:      S = F^{-1} τ F^{-T} (τ → S)
Lie derivative: L_v(τ) = F · (d/dt)(F^{-1} τ F^{-T}) · F^T
```

### Phase-Field Energy Split (Miehe)
```
ψ⁺ = λ/2 ⟨tr(ε)⟩₊² + μ tr(ε₊²)    (tension, degraded)
ψ⁻ = λ/2 ⟨tr(ε)⟩₋² + μ tr(ε₋²)    (compression, intact)
g(φ) = (1-φ)² + k                   (k ≈ 1e-6 for stability)
```

### FFT-Galerkin Essentials
```
Lippmann-Schwinger: ε̃(x) = -Γ⁰ * τ(ε̃)
Fourier space:      ε̂(ξ) = ε̄ - Γ̂⁰(ξ) : τ̂(ξ)
Green's operator:   Γ̂⁰ᵢⱼₖₗ(ξ) = Sym(ξₖ (K⁰)⁻¹ᵢₗ ξⱼ), K⁰ = C⁰ᵢⱼₖₗξⱼξₗ (acoustic tensor)
```

## Progressive disclosure map

### Tensor calculus and notation
- `reference/notation-cheatsheet.md`
- `reference/tensor-calculus.md`

### Kinematics: TL convected coordinates, large rotations/strains
- `reference/kinematics-tl-convected.md`
- `reference/objective-rates-integration.md`

### Plasticity: rate + temperature coupling
- `reference/constitutive-viscoplastic-thermo.md`
- `reference/constitutive-anisotropic-yield.md` (Barlat 2004-18p)

### Fracture: phase-field, brittle/ductile, GTN
- `reference/phase-field-fracture.md`
- `reference/ductile-fracture-gtn-phasefield.md`

### FFT-Galerkin micromechanics
- `reference/fft-galerkin-micromechanics.md`

### Solver architecture and validation
- `reference/solver-architecture-matrixfree.md`
- `reference/verification-benchmarks.md`

## Templates

Python skeletons (NumPy-first, easy to port to Taichi/JAX/PyTorch):

**Utilities:**
- `templates/tensor_ops.py` - Voigt conversions, deviator, Mises, polar decomposition

**Kinematics:**
- `templates/tl_convected_element.py` - Total Lagrangian element formulation

**Constitutive:**
- `templates/j2_perzyna_return_mapping.py` - J2 viscoplasticity with implicit integration
- `templates/barlat_2004_numpy.py` - Barlat 2004-18p anisotropic yield (NumPy, portable)
- `templates/barlat_2004_taichi.py` - Barlat 2004-18p (GPU-optimized Taichi implementation)

**Solvers:**
- `templates/newton_krylov_matrixfree.py` - Matrix-free Newton-Krylov solver
- `templates/fft_lippmann_schwinger.py` - FFT-Galerkin spectral solver

**Phase-field:**
- `templates/miehe_spectral_split.py` - Spectral energy split for fracture
- `templates/phasefield_staggered_solver.py` - Staggered phase-field solver

**Validation:**
- `templates/validation_benchmarks.py` - Canonical benchmark library (Taylor anvil, Sneddon crack, etc.)
- `templates/pytest_benchmarks_template.py` - Pytest wrapper for CI/CD integration

## Verification checklist (quick)

- Kinematics: correct $\nabla_X$ vs $\nabla_x$ usage, $J=\det F>0$.
- Stress pairing: TL uses $(S,E)$; spatial uses $(\sigma,D)$.
- Objectivity: rotating body does not create spurious stress.
- Plasticity: yield/flow/consistency are satisfied (or viscoplastic overstress is correct).
- Thermo: plastic dissipation produces $\Delta T$ with correct units/sign.
- Phase-field: irreversibility ($\dot\phi\ge 0$), no cracking in compression (energy split).
- FFT: zero-frequency handling, equilibrium residual in Fourier space decreases.
