---
id: damage-nonlocal-gradient
title: Nonlocal Gradient Damage Regularization
domain: computational-mechanics
subdomain: damage
tags:
- damage
- nonlocal
- gradient
- regularization
- mesh-objectivity
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-continuum-framework
  type: refines
  weight: 0.7
- to: damage-gtn-void-evolution
  type: feeds-into
  weight: 0.5
- to: fem-tl-weak-form
  type: requires
  weight: 1.0
- to: damage-nonlocal-integral
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Nonlocal Gradient Damage Regularization

## Summary

Nonlocal gradient damage regularization restores elliptic boundary value problems under strain-softening by introducing an internal length scale via a differential Helmholtz-type PDE for nonlocal strain.

## 1. Core Concept

Local continuum damage models undergoing strain-softening lose ellipticity in static problems and hyperbolicity in dynamic problems, leading to pathological mesh sensitivity where energy dissipation vanishes as the finite element mesh is refined. Nonlocal gradient damage regularization resolves this ill-posedness by formulating an implicit differential equation for a nonlocal equivalent strain field \bar{\varepsilon}, governed by an internal material length scale \ell. By coupling the local stress-strain update to the nonlocal strain field via a monolithic two-field finite element formulation, the width of the localization band is controlled independently of element size, preserving mesh objectivity and physical energy dissipation.

## 2. Mathematical Formulation

**Implicit Helmholtz Gradient Nonlocal Strain Equation**
$$
\bar{\varepsilon} - c \nabla^2 \bar{\varepsilon} = \tilde{\varepsilon}, \quad c = \frac{1}{2} \ell^2
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 212_

**Gradient Damage Boundary Condition**
$$
\nabla \bar{\varepsilon} \cdot \mathbf{n} = 0 \quad \text{on } S
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 212-213_

**Monolithic Two-Field Linearized Finite Element System**
$$
\begin{bmatrix} \mathbf{K}_{aa} & \mathbf{K}_{ae} \\ \mathbf{K}_{ea} & \mathbf{K}_{ee} \end{bmatrix} \begin{bmatrix} d\mathbf{a} \\ d\mathbf{e} \end{bmatrix} = \begin{bmatrix} \mathbf{f}_a^{ext} - \mathbf{f}_a^{int} \\ \mathbf{f}_e^{int} - \mathbf{K}_{ee} \mathbf{e} \end{bmatrix}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 213_

**Coupled Gradient Stiffness Sub-Block Definitions**
$$
\mathbf{K}_{aa} = \int_V (1 - \omega) \mathbf{B}^T \mathbf{D}^e \mathbf{B} dV, \quad \mathbf{K}_{ae} = \int_V q \mathbf{B}^T \mathbf{D}^e \bm{\varepsilon} \bar{\mathbf{H}} dV, \quad \mathbf{K}_{ee} = \int_V \left( \bar{\mathbf{H}}^T \bar{\mathbf{H}} + c \bar{\mathbf{B}}^T \bar{\mathbf{B}} \right) dV
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 213_

**Notation:**
\bar{\varepsilon}: nonlocal equivalent strain scalar field; \tilde{\varepsilon}: local strain-derived equivalent strain; \ell: internal material length scale parameter; c: gradient parameter (1/2 \ell^2); \mathbf{n}: outward boundary normal vector; \mathbf{a}: nodal displacement degree of freedom vector; \mathbf{e}: nodal nonlocal strain degree of freedom vector; \mathbf{K}_{aa}, \mathbf{K}_{ae}, \mathbf{K}_{ea}, \mathbf{K}_{ee}: sub-blocks of the monolithic gradient tangent stiffness matrix; \mathbf{B}: standard strain-displacement interpolation matrix; \bar{\mathbf{H}}: shape function array for nonlocal strain interpolation; \bar{\mathbf{B}}: spatial gradient matrix of \bar{\mathbf{H}}; \omega: scalar damage parameter; \kappa: historical maximum nonlocal strain.


## 3. Algorithmic Implementation

**Implicit Gradient Damage Monolithic Newton-Raphson Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given displacement field } \mathbf{a}_j, \text{ nonlocal strain } \mathbf{e}_j, \text{ damage history } \kappa_j, \text{ and external force increment } \Delta \mathbf{f}_a^{ext}$
\While{$\|\mathbf{r}_a\| > \text{TOL} \quad \text{or} \quad \|\mathbf{r}_e\| > \text{TOL}$}
\State $\bm{\varepsilon}_{j+1} = \mathbf{B} \mathbf{a}_{j+1}, \quad \tilde{\varepsilon}_{j+1} = \tilde{\varepsilon}(\bm{\varepsilon}_{j+1}), \quad \bar{\varepsilon}_{j+1} = \bar{\mathbf{H}} \mathbf{e}_{j+1}$
\State $f = \bar{\varepsilon}_{j+1} - \kappa_j$
\If{$f \ge 0$}
\State $\kappa_{j+1} = \bar{\varepsilon}_{j+1}, \quad q = \frac{\partial \omega}{\partial \kappa}$
\Else
\EndIf
\State $\omega_{j+1} = \omega(\kappa_{j+1}), \quad \bm{\sigma}_{j+1} = (1 - \omega_{j+1}) \mathbf{D}^e : \bm{\varepsilon}_{j+1}$
\State $\mathbf{K}_{aa} = \int_V (1 - \omega_{j+1}) \mathbf{B}^T \mathbf{D}^e \mathbf{B} dV, \quad \mathbf{K}_{ae} = \int_V q \mathbf{B}^T \mathbf{D}^e \bm{\varepsilon}_{j+1} \bar{\mathbf{H}} dV$
\State $\mathbf{K}_{ea} = \int_V \bar{\mathbf{H}}^T \frac{\partial \tilde{\varepsilon}}{\partial \bm{\varepsilon}} \mathbf{B} dV, \quad \mathbf{K}_{ee} = \int_V \left( \bar{\mathbf{H}}^T \bar{\mathbf{H}} + c \bar{\mathbf{B}}^T \bar{\mathbf{B}} \right) dV$
\State $\mathbf{r}_a = \mathbf{f}_a^{ext} - \int_V \mathbf{B}^T \bm{\sigma}_{j+1} dV, \quad \mathbf{r}_e = \int_V \bar{\mathbf{H}}^T \tilde{\varepsilon}_{j+1} dV - \mathbf{K}_{ee} \mathbf{e}_{j+1}$
\State $\text{Solve 2-field linear system: } \begin{bmatrix} \mathbf{K}_{aa} & \mathbf{K}_{ae} \\ \mathbf{K}_{ea} & \mathbf{K}_{ee} \end{bmatrix} \begin{bmatrix} d\mathbf{a} \\ d\mathbf{e} \end{bmatrix} = \begin{bmatrix} \mathbf{r}_a \\ \mathbf{r}_e \end{bmatrix}$
\State $\mathbf{a}_{j+1} = \mathbf{a}_{j+1} + d\mathbf{a}, \quad \mathbf{e}_{j+1} = \mathbf{e}_{j+1} + d\mathbf{e}$
\EndWhile
\Return $\text{Return updated displacements } \mathbf{a}_{j+1}, \text{ nonlocal strains } \mathbf{e}_{j+1}, \text{ and Cauchy stress } \bm{\sigma}_{j+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 6.5, p. 213-214_


## 4. Known Pitfalls

- **Spurious Non-Symmetry in Monolithic System Matrix**: The off-diagonal coupling blocks K_ae and K_ea in implicit gradient damage are inherently non-symmetric due to the derivative of damage with respect to history q = \partial \omega / \partial \kappa; forcing a symmetric solver discards cross-coupling terms and degrades global Newton convergence. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 213)_
- **C1-Continuity Requirements in Explicit Second-Order Gradient Models**: Evaluating second-order spatial gradients of local equivalent strain \nabla^2 \tilde{\varepsilon} directly in explicit gradient damage models requires third-order displacement derivatives, necessitating C1-continuous shape functions unless transformed into an implicit PDE. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 211-212)_
- **Spurious Damage Broadening Near Zero-Flux Boundaries**: Enforcing the natural boundary condition \nabla \bar{\varepsilon} \cdot \mathbf{n} = 0 on non-physical boundary locations artificially forces damage profiles to remain orthogonal to domain edges, introducing artificial boundary layer broadening. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 212-213; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 290)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Sarkar - A Computationally Efficient Vectorized Implementation of Localizing Gradient Damage Method in MATLAB.pdf
