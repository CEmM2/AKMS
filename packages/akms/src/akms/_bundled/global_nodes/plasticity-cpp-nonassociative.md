---
id: plasticity-cpp-nonassociative
title: Closest Point Projection for Non-J2 Surfaces
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- closest-point-projection
- non-associative
- drucker-prager
- multi-surface
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-general-return-mapping
  type: refines
  weight: 1.0
- to: plasticity-drucker-prager
  type: feeds-into
  weight: 1.0
- to: plasticity-hill48
  type: feeds-into
  weight: 0.8
- to: damage-gtn-yield-function
  type: feeds-into
  weight: 0.8
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Closest Point Projection for Non-J2 Surfaces

## Summary

The closest point projection algorithm for general non-J2 and non-associative yield surfaces solves the discrete backward Euler return-mapping system by enforcing plastic yield consistency alongside non-associated plastic flow rules.

## 1. Core Concept

The Closest Point Projection (CPP) algorithm for general non-J2 and non-associative yield criteria integrates elastoplastic constitutive equations over finite strain increments. When plastic flow direction \bm{m} = \partial g / \partial \bm{\sigma} differs from yield surface normal \bm{n} = \partial f / \partial \bm{\sigma} (such as in pressure-dependent Drucker-Prager or Mohr-Coulomb models where dilatancy angle \psi is smaller than friction angle \phi), trial elastic stress states \bm{\sigma}^{\mathrm{tr}} lie outside the admissible yield surface. The algorithm computes updated stress \bm{\sigma}_{n+1} and discrete plastic multiplier \Delta \gamma by iteratively solving a system of nonlinear residual equations using Newton-Raphson iterations with exact algorithmic Hessian matrices.

## 2. Mathematical Formulation

**Discrete Backward Euler Stress Update with Non-Associative Flow**
$$
\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}} - \Delta \gamma \mathbf{D}^e : \mathbf{m}_{n+1}, \quad \mathbf{m}_{n+1} = \left. \frac{\partial g}{\partial \bm{\sigma}} \right|_{n+1}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 143-145; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 251-252_

**Non-Associative Flow Potential for Drucker-Prager Plasticity**
$$
g(\bm{\sigma}) = \sqrt{J_2} + \alpha_g I_1 - k_g, \quad \alpha_g = \frac{2 \sin\psi}{\sqrt{3}(3 - \sin\psi)}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 228-232; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598_

**Local Newton Residual System for General CPP**
$$
\bm{R}(\bm{\sigma}_{n+1}, \Delta \gamma) = \begin{bmatrix} \mathbf{D}^{e-1} : (\bm{\sigma}_{n+1} - \bm{\sigma}^{\mathrm{tr}}) + \Delta \gamma \mathbf{m}_{n+1} \\ f(\bm{\sigma}_{n+1}, \bm{q}_{n+1}) \end{bmatrix} = \bm{0}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.5, p. 146; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 251-252_

**Non-Symmetric Algorithmic Hessian Tensor**
$$
\mathbf{\Xi}_{n+1} = \left[ \mathbf{D}^{e-1} + \Delta \gamma \frac{\partial^2 g}{\partial \bm{\sigma}_{n+1}^2} \right]^{-1}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 144, 213; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 252_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; \bm{\sigma}^{\mathrm{tr}}: trial elastic stress tensor; \mathbf{D}^e: fourth-order elastic stiffness tensor; \Delta \gamma: discrete plastic consistency multiplier; f: yield function; g: plastic potential function; \mathbf{n}: yield surface normal tensor (\partial f / \partial \bm{\sigma}); \mathbf{m}: plastic flow direction tensor (\partial g / \partial \bm{\sigma}); \psi: dilatancy angle; \phi: friction angle; \mathbf{\Xi}: modified algorithmic elasticity matrix; \bm{R}: local Newton residual vector.


## 3. Algorithmic Implementation

**Non-Associative Closest Point Projection Return-Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: stress } \bm{\sigma}_n, \text{ internal variables } \bm{q}_n, \text{ and strain increment } \Delta \bm{\varepsilon}$
\State $\bm{\sigma}^{\mathrm{tr}} = \bm{\sigma}_n + \mathbf{D}^e : \Delta \bm{\varepsilon}, \quad \bm{q}^{\mathrm{tr}} = \bm{q}_n, \quad f^{\mathrm{tr}} = f(\bm{\sigma}^{\mathrm{tr}}, \bm{q}^{\mathrm{tr}})$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}}, \quad \bm{q}_{n+1} = \bm{q}^{\mathrm{tr}}, \quad \bm{\varepsilon}^p_{n+1} = \bm{\varepsilon}^p_n$
\Return $\text{Step is elastic; return trial state}$
\Else
\EndIf
\While{$\|\bm{R}_{\bm{\sigma}}^{(k)}\| > \text{TOL}_1 \quad \text{or} \quad |f^{(k)}| > \text{TOL}_2$}
\State $\mathbf{n}^{(k)} = \left.\frac{\partial f}{\partial \bm{\sigma}}\right|_{n+1}^{(k)}, \quad \mathbf{m}^{(k)} = \left.\frac{\partial g}{\partial \bm{\sigma}}\right|_{n+1}^{(k)}, \quad \mathbf{H}_g^{(k)} = \left.\frac{\partial^2 g}{\partial \bm{\sigma}^2}\right|_{n+1}^{(k)}$
\State $\mathbf{\Xi}^{(k)} = \left[ \mathbf{D}^{e-1} + \Delta \gamma^{(k)} \mathbf{H}_g^{(k)} \right]^{-1}$
\State $d\Delta \gamma = \frac{f^{(k)} - \mathbf{n}^{(k)} : \mathbf{\Xi}^{(k)} : \bm{R}_{\bm{\sigma}}^{(k)}}{\mathbf{n}^{(k)} : \mathbf{\Xi}^{(k)} : \mathbf{m}^{(k)} + H_{\mathrm{alg}}^{(k)}}$
\State $d\bm{\sigma} = -\mathbf{\Xi}^{(k)} : \left[ \bm{R}_{\bm{\sigma}}^{(k)} + d\Delta \gamma \mathbf{m}^{(k)} \right]$
\State $\bm{\sigma}_{n+1}^{(k+1)} = \bm{\sigma}_{n+1}^{(k)} + d\bm{\sigma}, \quad \Delta \gamma^{(k+1)} = \Delta \gamma^{(k)} + d\Delta \gamma$
\State $k = k + 1$
\EndWhile
\State $\bm{\varepsilon}^p_{n+1} = \bm{\varepsilon}^p_n + \Delta \gamma \mathbf{m}_{n+1}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ plastic strain } \bm{\varepsilon}^p_{n+1}, \text{ and internal variables } \bm{q}_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.5, p. 146; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.7, p. 252_


## 4. Known Pitfalls

- **Loss of Symmetry in Algorithmic Tangent for Non-Associative Flow**: When plastic potential g differs from yield function f (e.g. \psi < \phi in frictional materials), the linearized algorithmic tangent tensor D^{alg} is non-symmetric; forcing a symmetric global solver discards off-diagonal terms, degrading Newton-Raphson convergence. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.7, p. 251-252; Simo_Hughes_1998_Computational inelasticity.pdf p. 147)_
- **Singular Hessian Inversion at Non-Smooth Yield Surface Corners**: Evaluating second derivatives \partial^2 g / \partial \bm{\sigma}^2 at non-smooth singular points (such as the apex or edges of Drucker-Prager or Mohr-Coulomb surfaces) causes division by zero and ill-conditioning unless subdifferential multi-surface or apex return mapping algorithms are used. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 212-215; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598; Simplify_radial_return_Part_1.pdf p. 1-2)_
- **Spurious Plastic Volume Expansion under Frictional Compression**: Assuming associative plastic flow (g = f) in pressure-dependent soil, concrete, or rock plasticity overpredicts volumetric plastic expansion (dilatancy); non-associated flow rules with independent dilatancy angles \psi < \phi are required to accurately model volumetric compaction. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 231-232; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Simplify_radial_return_Part_1.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
