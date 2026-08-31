---
id: damage-nonlocal-integral
title: Nonlocal Integral Damage Regularization
domain: computational-mechanics
subdomain: damage
tags:
- damage
- nonlocal
- integral
- regularization
- mesh-objectivity
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-continuum-framework
  type: refines
  weight: 0.7
- to: damage-nonlocal-gradient
  type: refines
  weight: 0.7
- to: damage-gtn-void-evolution
  type: feeds-into
  weight: 0.5
- to: fem-tl-weak-form
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Nonlocal Integral Damage Regularization

## Summary

Nonlocal integral damage regularization restores objectivity in strain-softening continuum models by replacing local equivalent strain with a spatially weighted integral average over the domain.

## 1. Core Concept

In local continuum damage models, strain-softening causes ill-posedness and severe mesh sensitivity, where localization bands collapse to a single element width and dissipated energy approaches zero upon mesh refinement. Nonlocal integral damage regularization resolves this pathological behavior by defining the damage loading criterion in terms of a nonlocal equivalent strain field \bar{\varepsilon}(\bm{x}). This nonlocal strain is computed as a spatially weighted integral average of the local equivalent strain \tilde{\varepsilon}(\bm{y}) using an averaging kernel \psi(\bm{y}, \bm{x}) and a normalization factor \Omega(\bm{x}). The spatial integration introduces an internal material length scale \ell, ensuring that the failure process zone width and energy dissipation remain finite and independent of finite element discretizations.

## 2. Mathematical Formulation

**Nonlocal Integral Strain Averaging Equation**
$$
\bar{\varepsilon}(\mathbf{x}) = \frac{1}{\Omega(\mathbf{x})} \int_V \psi(\mathbf{y}, \mathbf{x}) \tilde{\varepsilon}(\mathbf{y}) dV, \quad \Omega(\mathbf{x}) = \int_V \psi(\mathbf{y}, \mathbf{x}) dV
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 211_

**Isotropic Gaussian Spatial Weight Kernel**
$$
\psi(s) = \frac{1}{\sqrt{2\pi} \ell} \exp\left( -\frac{s^2}{2 \ell^2} \right), \quad s = \|\mathbf{x} - \mathbf{y}\|
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 211_

**Discrete Numerical Quadrature for Nonlocal Strain**
$$
\bar{\varepsilon}_{j+1}(\mathbf{x}) = \sum_i w_i \psi(\mathbf{y}_i, \mathbf{x}) \tilde{\varepsilon}_{j+1}(\mathbf{y}_i) V_{elem}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 6.4, p. 211_

**Nonlocal Damage Loading Criterion**
$$
f(\bar{\varepsilon}, \kappa) = \bar{\varepsilon} - \kappa \le 0, \quad \dot{\kappa} \ge 0, \quad f \dot{\kappa} = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 6.4, p. 211_

**Notation:**
\bar{\varepsilon}: nonlocal equivalent strain scalar field; \tilde{\varepsilon}: local equivalent strain measure; \mathbf{x}, \mathbf{y}: spatial position vectors; \psi(\mathbf{y}, \mathbf{x}): spatial averaging weight kernel function; \Omega(\mathbf{x}): spatial normalization volume factor; s: Euclidean distance \|\mathbf{x} - \mathbf{y}\|; \ell: internal material length scale; \kappa: internal damage history parameter; w_i: numerical integration weight at Gauss point i; V_{elem}: finite element volume contribution.


## 3. Algorithmic Implementation

**Nonlocal Integral Damage State Update Algorithm**
$$
\begin{algorithmic}
\State $\text{Given total strain increment } \Delta \bm{\varepsilon}_{j+1}, \text{ previous strain } \bm{\varepsilon}_j, \text{ and previous damage history } \kappa_0$
\State $\bm{\varepsilon}_{j+1} = \bm{\varepsilon}_j + \Delta \bm{\varepsilon}_{j+1}$
\State $\tilde{\varepsilon}_{j+1}(\bm{x}) = \tilde{\varepsilon}(\bm{\varepsilon}_{j+1}(\bm{x})) \quad \text{at all Gauss integration points } \bm{x}$
\For{$\text{Each Gauss integration point } \bm{x} \text{ in domain } V$}
\State $\bar{\varepsilon}_{j+1}(\bm{x}) = \sum_i w_i \psi(\bm{y}_i, \bm{x}) \tilde{\varepsilon}_{j+1}(\bm{y}_i) V_{elem}$
\EndFor
\If{$\bar{\varepsilon}_{j+1}(\bm{x}) - \kappa_0 \ge 0$}
\State $\kappa_{j+1} = \bar{\varepsilon}_{j+1}(\bm{x})$
\Else
\EndIf
\State $\omega_{j+1} = \omega(\kappa_{j+1})$
\State $\bm{\sigma}_{j+1} = (1 - \omega_{j+1}) \mathbf{D}^e : \bm{\varepsilon}_{j+1}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{j+1} \text{ and history } \kappa_{j+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 6.4, p. 211_


## 4. Known Pitfalls

- **Loss of Stiffness Matrix Symmetry in Implicit Solvers**: Averaging local strain fields across neighboring elements breaks the local symmetry of the strain-displacement operator, causing the global tangential stiffness matrix to become non-symmetric and increasing bandwidth. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 211; Sarkar - A Computationally Efficient Vectorized Implementation of Localizing Gradient Damage Method in MATLAB.pdf p. 3)_
- **Spurious Boundary Distortions from Unnormalized Weight Kernels**: Failing to normalize the spatial weight function by \Omega(\bm{x}) = \int_V \psi(\bm{y}, \bm{x}) dV near domain boundaries causes artificial reduction of nonlocal strain, resulting in unphysical damage suppression along specimen edges. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 211)_
- **Quadratic Computational Complexity for Full Domain Integration**: Evaluating spatial integrals over all Gauss point pairs scales quadratically with the total number of integration points (O(N^2)), causing severe computational bottlenecks in large 3D finite element meshes unless truncated to local neighborhoods. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 211; Sarkar - A Computationally Efficient Vectorized Implementation of Localizing Gradient Damage Method in MATLAB.pdf p. 2-3)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Sarkar - A Computationally Efficient Vectorized Implementation of Localizing Gradient Damage Method in MATLAB.pdf
